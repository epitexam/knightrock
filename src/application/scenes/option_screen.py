"""A screen that lists options and applies one on selection.

Every settings choice with more than a handful of values gets one of these
rather than a ←/→ cycle, and the reason is arithmetic rather than taste. The
driver reports 28 fullscreen modes on the development panel, so a cycle needs up
to 27 presses to reach one -- and a player who does not know the value exists
has no way to learn it exists at all. A list shows every option, marks the one in
force, and takes one press.

**Apply on selection, not on highlight.** Moving the highlight through the list
changes nothing; picking an entry applies it and closes. The alternative --
applying as the highlight moves -- looks better and is a trap: scrolling through
28 resolutions would rebuild the window 28 times, and a player browsing would
leave the game in whatever they happened to scroll past. Highlight is a cursor,
selection is a choice, and only the second one is a decision the player made.

One class rather than one per setting, deliberately. Four bespoke pickers is four
places for the keyboard, the mouse and the gamepad to disagree about what Enter
does, and that class of bug has already cost this menu twice -- six of nine rows
answered a click and none of them changed anything. Every picker here gets the
same behaviour because there is only one implementation of it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pygame

from src.application.scene import Scene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


@dataclass(frozen=True)
class Option:
    """One choice, with enough context to choose it without guessing.

    ``detail`` is what makes the list usable rather than merely navigable: two
    fit policies are words, and "fills the window, cropping the edges" is the
    difference between a player picking one on purpose and picking whichever came
    first.

    ``value`` is compared against ``selected`` to draw the check. It is compared
    by equality rather than by index, so a list can be filtered or reordered
    without the mark drifting onto the wrong entry -- the failure a fixed index
    has whenever the source list is rebuilt, which is every frame the topology
    changes.
    """

    label: str
    value: Any
    detail: str = ""
    enabled: bool = True

    def matches(self, selected: Any) -> bool:
        """Whether this is the option in force.

        ``is`` for the sentinels and ``==`` for the rest, because a tuple of
        ints compares fine while a freshly built enum member does not always
        identify by value across a rebuild.
        """
        if self.value is selected:
            return True
        try:
            return bool(self.value == selected)
        except Exception:  # noqa: BLE001 - an odd __eq__ is not worth a crash
            return False


@dataclass
class OptionScreen(Scene):
    """A list of options; picking one applies it and returns.

    ``apply`` is called with the chosen option's ``value``. It is expected to do
    the work immediately -- that is the contract that makes apply-on-selection
    honest -- and this screen does not wait for it or check its result. A setting
    that cannot be honoured says so in its own row, which is a better place for
    that than a modal would be.
    """

    game: Game
    title: str
    options: Sequence[Option]
    apply: Callable[[Any], None]
    selected: Any = None
    footer: str = "↑↓ row · Enter select · Esc back"
    #: Shown above the list, for the two or three words of orientation a
    #: settings list benefits from ("what this setting does").
    subtitle: str = ""
    on_back: Callable[[], None] | None = None
    view: MenuView = field(init=False)
    model: MenuModel = field(init=False)

    def __init__(
        self,
        game: Game,
        title: str,
        options: Sequence[Option],
        apply: Callable[[Any], None],
        *,
        selected: Any = None,
        footer: str = "↑↓ row · Enter select · Esc back",
        subtitle: str = "",
        on_back: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(game)
        self.title = title
        self.options = tuple(options)
        self.apply = apply
        self.selected = selected
        self.footer = footer
        self.subtitle = subtitle
        self.on_back = on_back
        self.view = MenuView(game.ui_scale)
        self.model = MenuModel(self._items(), selected=self._index_of(selected))
        #: How many rows the last draw actually painted, and the panel it made.
        #: Read back rather than recomputed, so the scroll arithmetic and the
        #: layout arithmetic cannot disagree about how tall a row is.
        self._last_visible: int | None = None
        self._last_panel_height = 0
        self.set_ui_scale(game.ui_scale)

    # ------------------------------------------------------------------ rows

    def _items(self) -> tuple[MenuItem, ...]:
        """The options as rows, plus a Back row.

        The mark is a leading ``●`` on the label rather than a column, because
        the value column is right-aligned and a right-aligned checkmark reads as
        the end of a long value at a glance. The label is where the eye already
        is.
        """
        rows = [
            MenuItem(
                f"option:{index}",
                ("● " if option.matches(self.selected) else "") + option.label,
                enabled=option.enabled,
            )
            for index, option in enumerate(self.options)
        ]
        rows.append(MenuItem("back", "Back"))
        return tuple(rows)

    def _index_of(self, selected: Any) -> int:
        """Where the cursor starts: on the option in force.

        Opening a list with the cursor at the top makes the player hunt for where
        they already were, which is the one fact the list is showing them.
        """
        for index, option in enumerate(self.options):
            if option.matches(selected):
                return index
        return 0

    def _rebuild(self, selected: Any) -> None:
        """Rebuild the rows around a new ``selected``, keeping the cursor put."""
        cursor = self.model.current_index
        self.selected = selected
        self.model.set_items(self._items(), cursor)

    # --------------------------------------------------------------- routing

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed: RoutedInput) -> str | None:
        if routed.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            # A controller losing a connection means "this input is gone", not
            # "leave this screen" -- the same reading every other screen takes.
            if routed.variant == "device_removed":
                return None
            self._leave()
            return MenuAction.BACK

        action, _ = self.model.handle_routed(
            routed.action, routed.position, self.view.item_rects, routed.variant
        )
        if action is None:
            return None
        if action == "back":
            self._leave()
            return MenuAction.BACK
        if action.startswith("option:"):
            self._choose(int(action.partition(":")[2]))
        return action

    def _choose(self, index: int) -> None:
        """Apply the option and go back to the screen that opened this one.

        Applied *before* the pop, so the caller sees the change while it is still
        on the stack and can refresh itself against it -- which is what keeps the
        row the player came from reading correctly the moment they land back on
        it, rather than one frame later.
        """
        if not 0 <= index < len(self.options):
            return
        option = self.options[index]
        if not option.enabled:
            # Silently ignored rather than closing: an entry that cannot be used
            # is one the player should see refuse, not one that looks like it
            # worked.
            return
        self.apply(option.value)
        self._leave()

    def _leave(self) -> None:
        """Pop, unless the opener asked to be told instead.

        ``on_back`` exists for the case where the submenu's result matters to
        more than the submenu: picking a monitor has to reach the runtime, and
        returning through the normal pop would leave the opener refreshing against
        a settings object the runtime never saw.
        """
        if self.on_back is not None:
            self.on_back()
        self.game.scene_manager.pop()

    # ------------------------------------------------------------------ draw

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)

    def _scroll_for(self, focused: int) -> int:
        """Keep the cursor on screen, one row of margin above and below.

        A list taller than the window has to scroll, because a row is never
        shorter than its text -- so a list cannot be squeezed to fit and there is
        no alternative to moving it. One row of margin rather than none, because
        a cursor pinned to the very edge reads as the end of the list rather than
        as a position within it.

        Measured on the worst case, 28 modes in a 640x480 window: twelve rows
        visible at scale 0.8, which without this would have put the twenty-eighth
        option permanently out of reach.
        """
        if focused <= 0:
            return 0
        visible = max(1, len(self.model.items))
        # The view decides how many fit; asking it is cheaper than duplicating
        # its arithmetic here, and a second copy would drift.
        return max(0, min(focused - 1, max(0, visible - self._visible_rows())))

    def _visible_rows(self) -> int:
        """How many rows the window shows at this scale.

        Measured once per draw from the panel the view produced last frame,
        which is the same measurement the view made. A first frame has no panel
        yet, so the full list is assumed and the scroll is clamped again on the
        next one.
        """
        return max(1, self._last_visible or len(self.model.items))

    def draw(self, surface: pygame.Surface) -> None:
        self.view.set_scale(self.game.ui_scale)
        focused_index = self.model.current_index
        focused = self.model.current_item
        panel = self.view.draw(
            surface,
            self.title,
            self.model,
            top=140 if self.subtitle else 180,
            description=self._description_for(focused),
            footers=(self.footer,) if self.footer else (),
            scroll=self._scroll_for(focused_index),
            scrollable=True,
        )
        # Remembered for the next frame's scroll decision, so the arithmetic that
        # decided what is on screen lives in exactly one place.
        drawn = sum(1 for rect in self.view.item_rects if rect.width > 0)
        self._last_visible = drawn
        self._last_panel_height = panel.height

    def _description_for(self, focused: MenuItem | None) -> str:
        """The one description to show: the focused row's, if it has one.

        Only the focused row. A block of text under every row is a wall of text,
        and the one a player needs is the one they are looking at.
        """
        if focused is None or not focused.action.startswith("option:"):
            return ""
        index = int(focused.action.partition(":")[2])
        if not 0 <= index < len(self.options):
            return ""
        return self.options[index].detail
