from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.menu_scene import MenuScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.styles import TEXT_CRIT

if TYPE_CHECKING:
    from src.core.game import Game


class GameOverScene(Scene):
    TITLE = "GAME OVER"

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(game)
        self.level_id = level_id
        items = (MenuItem("retry", "Retry"), MenuItem("menu", "Back to menu"))
        self.OPTIONS = tuple(item.label for item in items)
        self.model = MenuModel(items)
        self.view = MenuView()

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if (
            routed_input.action is InputAction.UI_CANCEL
            and routed_input.variant != "device_removed"
        ):
            self.game.scene_manager.switch(MenuScene(self.game))
            return
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "retry":
            self.game.scene_manager.switch(GameplayScene(self.game, self.level_id))
        elif action == "menu":
            self.game.scene_manager.switch(MenuScene(self.game))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        surface.fill((16, 8, 10))
        self.view.draw(surface, self.TITLE, self.model, top=240, title_color=TEXT_CRIT)
        return None
