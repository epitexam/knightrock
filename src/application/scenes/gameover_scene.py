"""Game Over scene (Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_panel import draw_centered_menu_panel
from src.application.scenes.menu_scene import MenuScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_CRIT, TEXT_OK

if TYPE_CHECKING:
    from src.core.game import Game


class GameOverScene(Scene):
    """Shown after ``Gameplay.MAX_DEATHS`` deaths: retry or menu."""

    TITLE = "GAME OVER"
    OPTIONS = ("ENTER: retry", "Q: menu")

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(game)
        self.level_id = level_id

    def update(self, delta_time: float) -> None:
        """Game over: nothing to simulate."""

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if routed_input.action is InputAction.UI_CONFIRM:
            self.game.scene_manager.switch(GameplayScene(self.game, self.level_id))
        elif (
            routed_input.action is InputAction.UI_CANCEL
            and routed_input.variant != "device_removed"
        ):
            self.game.scene_manager.switch(MenuScene(self.game))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:  # pragma: no cover - requires a broken display
            return None
        surface.fill((16, 8, 10))

        renderer = PanelRenderer(surface)
        draw_centered_menu_panel(
            renderer,
            surface,
            self.TITLE,
            list(self.OPTIONS),
            top=240,
            title_color=TEXT_CRIT,
            text_color=TEXT_OK,
        )
        return None
