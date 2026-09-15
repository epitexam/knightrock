"""Game Over scene (Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_panel import draw_centered_menu_panel
from src.application.scenes.menu_scene import MenuScene
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

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.game.scene_manager.switch(GameplayScene(self.game, self.level_id))
        elif event.key == pygame.K_q:
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
