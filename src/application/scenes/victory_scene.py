from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.application.scenes.level_select_scene import LevelSelectScene
from src.application.scenes.menu_scene import MenuScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.styles import TEXT_OK

if TYPE_CHECKING:
    from src.core.game import Game


class VictoryScene(Scene):
    TITLE = "VICTORY"

    def __init__(self, game: Game, level_id: int) -> None:
        super().__init__(game)
        self.level_id = level_id
        self.model = MenuModel(
            (
                MenuItem("retry", "Retry"),
                MenuItem("levels", "Level select"),
                MenuItem("menu", "Main menu"),
            )
        )
        self.view = MenuView()

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if routed_input.action is InputAction.UI_BACK:
            self.game.scene_manager.switch(MenuScene(self.game))
            return MenuAction.BACK
        if routed_input.action is InputAction.UI_CANCEL:
            # Bouton B (manette) = retour menu, comme ESC / clic droit.
            # (device_removed = manette débranchée : on retourne au menu aussi.)
            self.game.scene_manager.switch(MenuScene(self.game))
            return MenuAction.BACK
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "retry":
            self.game.scene_manager.switch(GameplayScene(self.game, self.level_id))
        elif action == "levels":
            self.game.scene_manager.push(LevelSelectScene(self.game))
        elif action == "menu":
            self.game.scene_manager.switch(MenuScene(self.game))
        return action

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        surface.fill((12, 20, 14))
        self.view.draw(surface, self.TITLE, self.model, top=190, title_color=TEXT_OK)
        return None
