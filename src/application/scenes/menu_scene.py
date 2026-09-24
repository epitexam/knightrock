from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.core.colors import Colors
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class MenuScene(Scene):
    TITLE = "KNIGHTROCK"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        save = game.save_game
        has_progress = save.last_level_id != 0 or len(save.unlocked_levels) > 1
        items: tuple[MenuItem, ...]
        self.options: tuple[str, ...]
        if has_progress:
            items = (
                MenuItem("continue", f"Continue (level {save.last_level_id})"),
                MenuItem("new_game", "New game"),
                MenuItem("options", "Options"),
                MenuItem("quit", "Quit"),
            )
            self.options = (
                f"ENTER: continue (level {save.last_level_id})",
                "N: new game",
                "OPTIONS",
                "ESC: quit",
            )
        else:
            items = (
                MenuItem("play", "Play"),
                MenuItem("options", "Options"),
                MenuItem("quit", "Quit"),
            )
            self.options = ("ENTER: play", "ESC: quit")
        self.model = MenuModel(items)
        self.view = MenuView()

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> None:
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "quit" or routed_input.action is InputAction.UI_BACK:
            self.game.running = False
        elif action in ("play", "continue"):
            save = self.game.save_game
            start_id = save.last_level_id if save.is_unlocked(save.last_level_id) else 0
            self.game.scene_manager.switch(GameplayScene(self.game, start_id))
        elif action == "new_game":
            self.game.scene_manager.switch(GameplayScene(self.game, 0))
        elif action == "options":
            from src.application.scenes.options_scene import OptionsScene

            self.game.scene_manager.push(OptionsScene(self.game))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        surface.fill(Colors.dark_grey)
        self.view.draw(surface, self.TITLE, self.model, top=180)
        return None
