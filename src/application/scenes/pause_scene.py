"""Pause scene (overlay above the frozen level, Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.menu_panel import draw_centered_menu_panel
from src.application.scenes.menu_scene import MenuScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_OK, TEXT_WARN

if TYPE_CHECKING:
    from src.core.game import Game


class PauseScene(Scene):
    """Pause overlay: resume, back to menu, quit."""

    TITLE = "PAUSE"
    OPTIONS = ("ENTER / ESC: resume", "Q: menu", "ESC FROM MENU: quit")

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(game)
        self.level_id = level_id

    def update(self, delta_time: float) -> None:
        """Paused: the frozen gameplay scene below does not advance."""

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if routed_input.action in (InputAction.UI_CONFIRM, InputAction.UI_BACK):
            self.game.scene_manager.pop()
        elif (
            routed_input.action is InputAction.UI_CANCEL
            and routed_input.variant != "device_removed"
        ):
            self.game.scene_manager.switch(MenuScene(self.game))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:  # pragma: no cover - requires a broken display
            return None
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((8, 10, 14, 190))
        surface.blit(overlay, (0, 0))

        renderer = PanelRenderer(surface)
        draw_centered_menu_panel(
            renderer,
            surface,
            self.TITLE,
            list(self.OPTIONS),
            top=220,
            title_color=TEXT_WARN,
            text_color=TEXT_OK,
        )
        return None
