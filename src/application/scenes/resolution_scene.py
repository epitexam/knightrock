"""Window size picker: a real list, and a list this machine can actually show.

The panel, the columns and the hints are the controls screen's, shared on
purpose -- a screen that lists sizes is a table, and a table should look like
one. What changed is where the rows come from.

The old list was seven absolute resolutions, which is a claim about the
player's monitor that the game has no way to check: on a 1366x768 laptop it
offered 2560x1440, and choosing it opened a window larger than the screen. The
list is now derived from the desktop, so every row is a fraction of the screen
in front of the player, and a row that would not fit is never drawn.

The ``STATE`` column reports three things, because ``Auto`` is now a real value
and not a synonym for "whatever is current": ``auto`` is the size the automatic
rule would pick on this machine, ``current`` is the one in use, and ``--`` is
merely on offer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.core.display.detection import (
    centered_on_primary,
    desktop_size,
    fits_on_desktop,
    largest_window_size,
    window_size_choices,
)
from src.core.display.mode import DisplayMode
from src.core.display.size_mode import SizeMode
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.grid_view import GridCell, GridRow, GridView
from src.ui.menu_model import MenuAction, MenuItem, MenuModel

if TYPE_CHECKING:
    from src.core.game import Game

#: Label gutter, inherited from the grid panel's own layout.
STATE_COLUMN = 0
AUTO_MARK = "auto"
CURRENT_MARK = "current"
EMPTY_MARK = "—"
BACK_HINT = "Esc / right click"


class ResolutionScene(Scene):
    TITLE = "WINDOW SIZE"
    FOOTER = "↑↓ row · Enter apply · Esc/B back"
    #: The panel's single value column, the same argument as the old STATE
    #: column: the size is the row label, like a binding name in the controls
    #: grid; this is what the row *reports* about itself.
    COLUMN_HEADERS = ("STATE",)

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = GridView(game.settings.ui_scale)
        self._signature = self._current_signature()
        self._rows: list[GridRow] = []
        self._rebuild()

    def _sizes(self) -> tuple[tuple[int, int], ...]:
        """The sizes on offer, smallest first.

        The automatic choice is always in the list, even when it coincides with
        a fraction: it is the row that says "this is what I would do", and
        hiding it would make ``Auto`` a value the player cannot select back to.
        """
        desktop = desktop_size()
        if desktop[0] <= 0 or desktop[1] <= 0:
            current = (self.game.settings.width, self.game.settings.height)
            return (current,) if fits_on_desktop(current, desktop) else ()
        sizes = set(window_size_choices(desktop))
        automatic = largest_window_size(desktop)
        if fits_on_desktop(automatic, desktop):
            sizes.add(automatic)
        return tuple(sorted(sizes))

    def _current_signature(self) -> tuple[object, ...]:
        settings = self.game.settings
        return (
            settings.width,
            settings.height,
            settings.size_mode,
            settings.display,
            desktop_size(),
        )

    def _rebuild(self, selected_action: str | None = None) -> None:
        settings = self.game.settings
        current = (settings.width, settings.height)
        automatic = largest_window_size(desktop_size())
        items: list[MenuItem] = []
        rows: list[GridRow] = []
        for width, height in self._sizes():
            label = f"{width} x {height}"
            items.append(MenuItem(f"res:{width}x{height}", label))
            rows.append(GridRow(label, (self._state_cell((width, height), current, automatic),)))
        items.append(MenuItem("back", "Back"))
        rows.append(GridRow("Back", (GridCell(BACK_HINT),)))
        self._rows = rows
        if selected_action is not None:
            # Keep the cursor where the player left it: rebuilding on every
            # frame would otherwise snap it back to the current size and make
            # the list impossible to walk down.
            selected = next(
                (i for i, item in enumerate(items) if item.action == selected_action),
                0,
            )
        else:
            selected = next(
                (index for index, size in enumerate(self._sizes()) if size == current),
                0,
            )
        self.model.set_items(items, selected)

    @classmethod
    def _state_cell(
        cls,
        size: tuple[int, int],
        current: tuple[int, int],
        automatic: tuple[int, int],
    ) -> GridCell:
        """What this row is, given what the settings currently say.

        Muted when it is neither in use nor the automatic choice, so the two
        rows that mean something are the two that read.
        """
        if size == current:
            return GridCell(CURRENT_MARK)
        if size == automatic:
            return GridCell(AUTO_MARK)
        return GridCell(EMPTY_MARK, muted=True)

    @property
    def rows(self) -> list[GridRow]:
        """The grid rows, index for index with ``model.items``.

        Public for the same reason ``ControlsScene.rows`` is: the panel draws
        exactly what the model navigates, and a test that checks the rendered
        column must not have to reach into the scene's private state.
        """
        return self._rows

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if routed_input.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            if routed_input.variant != "device_removed":
                self.game.scene_manager.pop()
                return MenuAction.BACK
            return None
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.row_rects, routed_input.variant
        )
        if action == "back":
            self.game.scene_manager.pop()
            return MenuAction.BACK
        if action is not None and action.startswith("res:"):
            width, height = (int(part) for part in action.removeprefix("res:").split("x"))
            self._select(width, height)
        return action

    def _select(self, width: int, height: int) -> None:
        """Apply the size and go back to the video menu.

        Picking a size is a decision, so the mode becomes ``MANUAL`` and the
        game stops second-guessing it on the next launch. It is still refused if
        it does not fit, which cannot happen through this list.
        """
        size = (width, height)
        if size == (self.game.settings.width, self.game.settings.height):
            self.game.scene_manager.pop()
            return
        self.game.apply_settings(
            self.game.settings.with_video(
                width=width,
                height=height,
                size_mode=SizeMode.MANUAL,
                display=(
                    self.game.settings.display
                    if self.game.settings.display.is_concrete
                    else DisplayMode.WINDOW
                ),
            )
        )
        self.game.scene_manager.pop()

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)

    def draw(self, surface: pygame.Surface) -> None:
        if self._current_signature() != self._signature:
            self._signature = self._current_signature()
            focused = self.model.current_item.action if self.model.current_item else None
            self._rebuild(focused)
        settings = self.game.settings
        self.view.set_scale(settings.ui_scale)
        self.view.draw(
            surface,
            self.TITLE,
            self._subtitle(),
            self.COLUMN_HEADERS,
            self._rows,
            selected_row=self.model.current_index,
            selected_column=STATE_COLUMN,
            top=80,
            footers=(self.FOOTER,),
        )

    def _subtitle(self) -> str:
        desktop = desktop_size()
        if desktop[0] <= 0:
            return "Screen size unknown"
        count = len(self._sizes())
        return f"Screen {desktop[0]} x {desktop[1]} - {count} window sizes fit"


def preview_centered(size: tuple[int, int], desktop: tuple[int, int]) -> tuple[int, int]:
    """Where a window of ``size`` would open on ``desktop``.

    Exposed so the menu's claim that a size "fits" is checkable: the size has
    to fit *and* still be reachable once centred.
    """
    return centered_on_primary(size, desktop)
