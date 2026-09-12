"""Scène de Game Over (Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_scene import MenuScene
from src.ui.styles import TEXT_CRIT, TEXT_OK

if TYPE_CHECKING:
    from src.core.game import Game


class GameOverScene(Scene):
    """Affichée après ``Gameplay.MAX_DEATHS`` morts : rejouer ou menu."""

    TITLE = "GAME OVER"
    OPTIONS = ("ENTRÉE : réessayer", "Q : menu")

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

        title_font = pygame.font.Font(None, 88)
        option_font = pygame.font.Font(None, 40)
        center = surface.get_width() // 2

        title = title_font.render(self.TITLE, True, TEXT_CRIT)
        title_rect = title.get_rect(midtop=(center, 240))
        surface.blit(title, title_rect)

        y = title_rect.bottom + 60
        for option in self.OPTIONS:
            text = option_font.render(option, True, TEXT_OK)
            text_rect = text.get_rect(midtop=(center, y))
            surface.blit(text, text_rect)
            y += text_rect.height + 16
        return None
