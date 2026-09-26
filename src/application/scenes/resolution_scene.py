"""Resolution picker: a real list instead of a blind cycle.

Cycling a single row forced the player to press ←/→ until the wanted value
appeared, with no way to see the options. This screen shows every supported
resolution at once and marks the one currently in use.

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
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.styles import TEXT_OK

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
    CURRENT_SUFFIX = "  (current)"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = MenuView(game.settings.ui_scale)
        self._signature = self._current_signature()
        self._rebuild()

    def _current_signature(self) -> tuple[int, int]:
        return (self.game.settings.width, self.game.settings.height)

    def _rebuild(self, selected_action: str | None = None) -> None:
        settings = self.game.settings
        current = (settings.width, settings.height)
        items = [
            MenuItem(f"res:{width}x{height}", self._label(width, height, current))
            for width, height in RESOLUTIONS
        ]
        items.append(MenuItem("back", "Back"))
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
    def _label(cls, width: int, height: int, current: tuple[int, int]) -> str:
        label = f"{width} x {height}"
        return label + cls.CURRENT_SUFFIX if (width, height) == current else label

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if routed_input.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            if routed_input.variant != "device_removed":
                self.game.scene_manager.pop()
                return MenuAction.BACK
            return None
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
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

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        # Refreshed only when the applied size actually changes (window
        # recreation can happen under this screen), so the "(current)" marker
        # follows the settings without touching the cursor the player moved.
        if self._current_signature() != self._signature:
            self._signature = self._current_signature()
            focused = self.model.current_item.action if self.model.current_item else None
            self._rebuild(focused)
        self.view.draw(surface, self.TITLE, self.model, top=120, title_color=TEXT_OK)
        return None
