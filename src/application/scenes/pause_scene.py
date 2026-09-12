"""Scène de pause (overlay au-dessus du niveau gelé, Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.menu_scene import MenuScene
from src.ui.styles import TEXT_OK, TEXT_WARN

if TYPE_CHECKING:
    from src.core.game import Game


class PauseScene(Scene):
    """Overlay de pause : reprendre, revenir au menu, quitter."""

    TITLE = "PAUSE"
    OPTIONS = ("ENTRÉE / ÉCHAP : reprendre", "Q : menu", "ÉCHAP DU MENU : quitter")

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(game)
        self.level_id = level_id

    def update(self, delta_time: float) -> None:
        """Paused: the frozen gameplay scene below does not advance."""

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
            self.game.scene_manager.pop()
        elif event.key == pygame.K_q:
            self.game.scene_manager.switch(MenuScene(self.game))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:  # pragma: no cover - requires a broken display
            return None
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((8, 10, 14, 190))
        surface.blit(overlay, (0, 0))

        title_font = pygame.font.Font(None, 72)
        option_font = pygame.font.Font(None, 36)
        center = surface.get_width() // 2

        title = title_font.render(self.TITLE, True, TEXT_WARN)
        title_rect = title.get_rect(midtop=(center, 220))
        surface.blit(title, title_rect)

        y = title_rect.bottom + 40
        for option in self.OPTIONS:
            text = option_font.render(option, True, TEXT_OK)
            text_rect = text.get_rect(midtop=(center, y))
            surface.blit(text, text_rect)
            y += text_rect.height + 12
        return None
