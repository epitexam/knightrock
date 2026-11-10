"""One base for every menu screen: rows, routing, scrolling, drawing.

Every menu used to carry its own copy of the same forty lines -- a model, a
view, a Back/Cancel branch, a ``device_removed`` filter, a ``top`` in raw pixels,
a draw -- and the copies drifted: one forgot the controller filter, one lost the
focus after a submenu, each sat at its own height. A screen now says what its
rows are and what they do; everything else is here, once.

Hooks a screen overrides:

- :meth:`act` -- a row fired (anything but ``back``);
- :meth:`leave` -- Back, Escape or the Back row (default: pop);
- :meth:`on_device_removed` -- a controller was unplugged (default: nothing);
- :meth:`handle_value_keys` -- ←/→/Enter on a value row, before the list sees them;
- :meth:`description`, :meth:`footers`, :meth:`highlighted` -- what the panel says;
- :meth:`draw_over` -- anything painted over the panel.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.core.input.event_router import InputDevice, RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.styles import TEXT_TITLE
from src.ui.text import DEVICE_KEYS, t

if TYPE_CHECKING:
    from src.core.game import Game

#: What the model reports when only the focus moved.
_NAVIGATION = frozenset({MenuAction.MOVE_UP, MenuAction.MOVE_DOWN, MenuAction.HOVER})


class MenuPage(Scene):
    """A titled list of rows in a panel."""

    TITLE = ""
    #: Where every page's panel sits, in design pixels of a 648-tall picture.
    #: One value for every page, so moving between pages turns a page rather
    #: than opening a box somewhere else.
    TOP = 170
    TITLE_COLOR: tuple[int, int, int] = TEXT_TITLE
    #: A colour the page fills the target with before drawing, or ``None``.
    BACKGROUND: tuple[int, int, int] | None = None
    #: The help line under the rows: a key of :mod:`src.ui.text`, filled with
    #: the keys of the device the player last used, or ``""`` for none.
    FOOTER = "footer.page"
    #: Whether a list taller than the window scrolls rather than running off it.
    scrollable = False
    covers_panels_below = True

    def __init__(self, game: Game, items: Sequence[MenuItem] = (), selected: int = 0) -> None:
        super().__init__(game)
        self.title = self.TITLE
        self.footer = self.FOOTER
        self.model = MenuModel(tuple(items), selected=selected)
        self.view: MenuView = MenuView(game.ui_scale)
        #: How many rows the last draw painted, the first one, and the panel.
        #: Read back from the draw so the scroll and the layout agree.
        self._last_visible: int | None = None
        self._scroll = 0
        self._panel: pygame.Rect | None = None
        #: The pointer's last y, which the scroll follows while it is on a row.
        self._pointer_y: int | None = None
        #: The device the player last used, which the help line names keys for.
        self._device = InputDevice.KEYBOARD

    # -------------------------------------------------------------- hooks

    def act(self, action: str) -> None:
        """A row fired. Nothing by default."""

    def leave(self) -> str | None:
        """Leave the page: Back, Escape, or the Back row."""
        self.game.scene_manager.pop()
        return MenuAction.BACK

    def on_back_key(self, action: InputAction) -> str | None:
        """Back or Cancel was pressed. Both leave by default."""
        return self.leave()

    def on_device_removed(self) -> str | None:
        """A controller was unplugged. That is not the player asking for anything."""
        return None

    def handle_value_keys(self, routed: RoutedInput) -> str | None:
        """←/→/Enter on a value row, before the list sees them. ``None`` passes."""
        return None

    def description(self) -> str:
        return ""

    def footers(self) -> tuple[str, ...]:
        if not self.footer:
            return ()
        keys = DEVICE_KEYS["gamepad" if self._device is InputDevice.GAMEPAD else "keyboard"]
        footer = t(self.footer, **keys)
        if (
            self.scrollable
            and self._last_visible is not None
            and self._last_visible < len(self.model.items)
        ):
            footer = f"{footer} · {t('footer.page_keys')}"
        return (footer,)

    def highlighted(self) -> int:
        return -1

    def draw_over(self, surface: pygame.Surface, panel: pygame.Rect) -> None:
        """Paint anything over the panel. Nothing by default."""

    # ------------------------------------------------------------ routing

    def update(self, delta_time: float) -> None:
        return None

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)

    def handle_routed(self, routed: RoutedInput) -> str | None:
        if routed.variant == "device_removed":
            return self.on_device_removed()
        if routed.device is not None:
            self._device = routed.device
        if routed.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            return self.on_back_key(routed.action)
        if self.scrollable:
            if routed.action in (InputAction.UI_SCROLL, InputAction.UI_SCROLL_UP):
                return self._wheel(routed)
            if routed.action is InputAction.UI_POINTER_DOWN and routed.position is not None:
                paged = self._page_from_rail(routed.position)
                if paged is not None:
                    return paged
            self._note_pointer(routed)
        value = self.handle_value_keys(routed)
        if value is not None:
            return value
        performed, _ = self.model.handle_routed(
            routed.action, routed.position, self.view.item_rects, routed.variant
        )
        return self._report(performed)

    def _report(self, performed: str | None) -> str | None:
        if performed is None or performed in _NAVIGATION:
            return performed
        if performed == "back":
            return self.leave()
        self.act(performed)
        return performed

    # ------------------------------------------------------------ scrolling

    def _wheel(self, routed: RoutedInput) -> str:
        """One row per notch. It moves the focus, never selects."""
        steps = max(1, int(routed.value or 1))
        self._pointer_y = None
        up = routed.action is InputAction.UI_SCROLL_UP
        for _ in range(steps):
            self.model.move(-1 if up else 1)
        return MenuAction.MOVE_UP if up else MenuAction.MOVE_DOWN

    def _note_pointer(self, routed: RoutedInput) -> None:
        """Remember the pointer's y; any other device makes the scroll follow the focus."""
        if routed.action is InputAction.UI_POINTER_MOVE and routed.position is not None:
            self._pointer_y = routed.position[1]
        elif routed.device is not InputDevice.MOUSE:
            self._pointer_y = None

    def _scroll_for(self, focused: int) -> int:
        """The first row to show.

        While the pointer is on a row, the list moves only to keep that row
        whole, by the least amount -- scrolling towards a pointer parked under
        the rows would make the list chase it to the end. Otherwise it follows
        the focus, one row from the edge.
        """
        visible = self._visible_rows()
        count = len(self.model.items)
        if count <= visible:
            return 0
        if self._pointer_y is not None:
            row = self._row_at(self._pointer_y)
            if row is not None:
                if row < self._scroll:
                    return max(0, row)
                if row >= self._scroll + visible:
                    return row - visible + 1
                return self._scroll
        return max(0, min(focused - 1, count - visible))

    def _visible_rows(self) -> int:
        return max(1, self._last_visible or len(self.model.items))

    def _row_at(self, y: int) -> int | None:
        """The painted row at ``y``, or ``None`` over the title, a gap or below."""
        for offset in range(self._visible_rows()):
            index = self._scroll + offset
            if not 0 <= index < len(self.model.items):
                break
            rect = self.view.item_rects[index]
            if rect.width > 0 and rect.top <= y < rect.bottom:
                return index
        return None

    def _rail_strip(self) -> pygame.Rect | None:
        """The clickable strip from the scroll rail to the panel's edge."""
        rail = self.view.scroll_rail
        if rail is None or self._panel is None:
            return None
        return pygame.Rect(rail.left, rail.top, self._panel.right - rail.left, rail.height)

    def _page_from_rail(self, position: tuple[int, int]) -> str | None:
        """A press on the rail pages towards it; on the thumb, nothing."""
        strip = self._rail_strip()
        thumb = self.view.scroll_thumb
        if strip is None or thumb is None or not strip.collidepoint(position):
            return None
        if thumb.top <= position[1] <= thumb.bottom:
            return None
        return self._page(-1 if position[1] < thumb.top else 1)

    def _page(self, direction: int) -> str | None:
        action = InputAction.UI_PAGE_DOWN if direction > 0 else InputAction.UI_PAGE_UP
        performed, _ = self.model.handle_routed(action, None, self.view.item_rects, None)
        return performed

    # ---------------------------------------------------------------- draw

    def draw(self, surface: pygame.Surface) -> None:
        if self.BACKGROUND is not None:
            surface.fill(self.BACKGROUND)
        self.view.set_scale(self.game.ui_scale)
        if self.scrollable:
            self._scroll = self._scroll_for(self.model.current_index)
        panel = self.view.draw(
            surface,
            self.title,
            self.model,
            top=self.TOP,
            title_color=self.TITLE_COLOR,
            highlighted=self.highlighted(),
            footers=self.footers(),
            description=self.description(),
            scroll=self._scroll,
            scrollable=self.scrollable,
        )
        self._last_visible = sum(1 for rect in self.view.item_rects if rect.width > 0)
        self._panel = panel
        self.draw_over(surface, panel)
