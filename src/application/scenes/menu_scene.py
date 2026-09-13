"""Scène de menu principal (audit F8.1, Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_panel import draw_centered_menu_panel
from src.core.colors import Colors
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_OK

if TYPE_CHECKING:
    from src.core.game import Game


class MenuScene(Scene):
    """Écran titre : continuer / nouveau jeu, ou quitter.

    Le rendu est volontairement textuel (scene minimal) : la priorité
    est la machine d'états d'application, pas l'habillage du menu.
    La progression affichée vient de :class:`SaveGame` (Phase 2 #6).
    """

    TITLE = "KNIGHTROCK"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        save = game.save_game
        has_progress = save.last_level_id != 0 or len(save.unlocked_levels) > 1
        self.options: tuple[str, ...]
        if has_progress:
            self.options = (
                f"ENTRÉE : continuer (niveau {save.last_level_id})",
                "N : nouveau jeu",
                "ÉCHAP : quitter",
            )
        else:
            self.options = ("ENTRÉE : jouer", "ÉCHAP : quitter")

    def update(self, delta_time: float) -> None:
        """A menu is static: nothing to simulate."""

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            save = self.game.save_game
            start_id = save.last_level_id if save.is_unlocked(save.last_level_id) else 0
            self.game.scene_manager.switch(GameplayScene(self.game, start_id))
        elif event.key == pygame.K_n and len(self.options) == 3:
            self.game.scene_manager.switch(GameplayScene(self.game, 0))
        elif event.key == pygame.K_ESCAPE:
            self.game.running = False

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:  # pragma: no cover - requires a broken display
            return None
        surface.fill(Colors.dark_grey)
        renderer = PanelRenderer(surface)
        draw_centered_menu_panel(
            renderer, surface, self.TITLE, list(self.options), top=180, text_color=TEXT_OK
        )
        return None
