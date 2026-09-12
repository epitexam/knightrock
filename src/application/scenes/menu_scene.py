"""Scène de menu principal (audit F8.1, Phase 2 #4)."""

from __future__ import annotations

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.core.colors import Colors
from src.ui.styles import TEXT_OK


class MenuScene(Scene):
    """Écran titre : lancer le jeu ou quitter.

    Le rendu est volontairement textuel (scene minimal) : la priorité
    est la machine d'états d'application, pas l'habillage du menu.
    """

    TITLE = "KNIGHTROCK"
    OPTIONS = ("ENTRÉE : jouer", "ÉCHAP : quitter")

    def update(self, delta_time: float) -> None:
        """A menu is static: nothing to simulate."""

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.game.scene_manager.switch(GameplayScene(self.game))
        elif event.key == pygame.K_ESCAPE:
            self.game.running = False

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:  # pragma: no cover - requires a broken display
            return None
        surface.fill(Colors.dark_grey)
        title_font = pygame.font.Font(None, 96)
        option_font = pygame.font.Font(None, 40)

        title = title_font.render(self.TITLE, True, Colors.gold)
        title_rect = title.get_rect(midtop=(surface.get_width() // 2, 180))
        surface.blit(title, title_rect)

        y = title_rect.bottom + 60
        for option in self.OPTIONS:
            text = option_font.render(option, True, TEXT_OK)
            text_rect = text.get_rect(midtop=(surface.get_width() // 2, y))
            surface.blit(text, text_rect)
            y += text_rect.height + 16
        return None
