"""Resolution picker: a real list instead of a blind cycle.

Cycling a single row forced the player to press ←/→ until the wanted value
appeared, with no way to see the options. This screen shows every supported
resolution at once, in the same grid panel the controls screen draws — title,
column headers, focus strip, hint line — with the size in use reported in its
own ``STATE`` column instead of a marker glued to the label, so the sizes line
up.

It is also the single source of truth for the preset list: ``VideoScene``
imports ``RESOLUTIONS`` from here, so the menu row and the picker can never
drift apart.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.grid_view import GridCell, GridRow, GridView
from src.ui.menu_model import MenuAction, MenuItem, MenuModel

if TYPE_CHECKING:
    from src.core.game import Game

#: Supported window sizes, smallest first. The window is not resizable, so this
#: list *is* the choice offered to the player.
RESOLUTIONS: tuple[tuple[int, int], ...] = (
    (1024, 576),
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
)


class ResolutionScene(Scene):
    TITLE = "RESOLUTION"
    #: The panel's single value column. The resolution itself is the row label,
    #: like a binding name in the controls grid; this is what the row *reports*:
    #: whether that size is the one in use.
    COLUMN_HEADERS = ("STATE",)
    #: The ring frames the cell the action changes: applying a row is what makes
    #: it "current", exactly as the ring on the controls grid frames the binding
    #: a capture would rewrite.
    STATE_COLUMN = 0
    CURRENT_MARK = "current"
    EMPTY_MARK = "—"
    BACK_HINT = "Esc / right click"
    FOOTER = "↑↓ row · Enter apply · Esc/B back"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = GridView(game.settings.ui_scale)
        self._signature = self._current_signature()
        self._rows: list[GridRow] = []
        self._rebuild()

    def _current_signature(self) -> tuple[int, int]:
        return (self.game.settings.width, self.game.settings.height)

    def _rebuild(self, selected_action: str | None = None) -> None:
        settings = self.game.settings
        current = (settings.width, settings.height)
        items: list[MenuItem] = []
        rows: list[GridRow] = []
        for width, height in RESOLUTIONS:
            label = f"{width} x {height}"
            items.append(MenuItem(f"res:{width}x{height}", label))
            rows.append(GridRow(label, (self._state_cell((width, height), current),)))
        items.append(MenuItem("back", "Back"))
        rows.append(GridRow("Back", (GridCell(self.BACK_HINT),)))
        self._rows = rows
        if selected_action is not None:
            # Keep the cursor where the player left it: rebuilding on every
            # frame would otherwise snap it back to the current resolution and
            # make the list impossible to walk down.
            selected = next(
                (i for i, item in enumerate(items) if item.action == selected_action),
                0,
            )
        else:
            selected = next(
                (index for index, (w, h) in enumerate(RESOLUTIONS) if (w, h) == current),
                0,
            )
        self.model.set_items(items, selected)

    @classmethod
    def _state_cell(cls, size: tuple[int, int], current: tuple[int, int]) -> GridCell:
        """The ``STATE`` column: what is in use, and what is merely on offer.

        The marker used to be appended to the label ("1440 x 900  (current)"),
        which is exactly what a column of values is for. Muting the other rows
        is what makes the real one readable at a glance.
        """
        if size == current:
            return GridCell(cls.CURRENT_MARK)
        return GridCell(cls.EMPTY_MARK, muted=True)

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
        """Apply the size, then fall back to the Video menu.

        Recreating the window is immediate: the logical size is the gameplay
        viewport, so it must not wait for a restart.
        """
        if (width, height) == (self.game.settings.width, self.game.settings.height):
            self.game.scene_manager.pop()
            return
        self.game.apply_settings(replace(self.game.settings, width=width, height=height))
        self.game.scene_manager.pop()

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)

    def draw(self, surface: pygame.Surface) -> None:
        # Refreshed only when the applied size actually changes (window
        # recreation can happen under this screen), so the "current" marker
        # follows the settings without touching the cursor the player moved.
        if self._current_signature() != self._signature:
            self._signature = self._current_signature()
            focused = self.model.current_item.action if self.model.current_item else None
            self._rebuild(focused)
        settings = self.game.settings
        self.view.set_scale(settings.ui_scale)
        self.view.draw(
            surface,
            self.TITLE,
            f"{settings.width} x {settings.height} in use",
            self.COLUMN_HEADERS,
            self._rows,
            selected_row=self.model.current_index,
            selected_column=self.STATE_COLUMN,
            top=80,
            footers=(self.FOOTER,),
        )
