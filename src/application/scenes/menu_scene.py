"""Main menu scene (audit F8.1, Phase 2 #4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_panel import draw_centered_menu_panel
from src.core.colors import Colors
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import TEXT_OK

if TYPE_CHECKING:
    from src.core.game import Game


class MenuScene(Scene):
    """Title screen: continue / new game, or quit.

    Rendering is deliberately textual (minimal scene): the priority is the
    application state machine, not menu dressing.  The displayed progression
    comes from :class:`SaveGame` (Phase 2 #6).
    """

    TITLE = "KNIGHTROCK"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        save = game.save_game
        has_progress = save.last_level_id != 0 or len(save.unlocked_levels) > 1
        self.options: tuple[str, ...]
        if has_progress:
            self.options = (
                f"ENTER: continue (level {save.last_level_id})",
                "N: new game",
                "ESC: quit",
            )
        else:
            self.options = ("ENTER: play", "ESC: quit")

    def update(self, delta_time: float) -> None:
        """A menu is static: nothing to simulate."""

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if routed_input.action is InputAction.UI_CONFIRM:
            if routed_input.variant == "new_game" and len(self.options) == 3:
                self.game.scene_manager.switch(GameplayScene(self.game, 0))
                return
            save = self.game.save_game
            start_id = save.last_level_id if save.is_unlocked(save.last_level_id) else 0
            self.game.scene_manager.switch(GameplayScene(self.game, start_id))
        elif routed_input.action is InputAction.UI_BACK:
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
