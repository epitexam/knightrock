from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.gameplay_scene import GameplayScene
from src.core.colors import Colors
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class LevelSelectScene(Scene):
    TITLE = "SELECT LEVEL"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        unlocked = set(game.save_game.unlocked_levels)
        items = tuple(
            MenuItem(
                f"level:{level_id}",
                f"Level {level_id}",
                level_id in unlocked,
            )
            for level_id in sorted(game.level_manager.level_paths)
        )
        self.model = MenuModel(items)
        self.view = MenuView()

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if routed_input.action is InputAction.UI_BACK:
            self.game.scene_manager.pop()
            return MenuAction.BACK
        # Bouton B (manette) = retour, comme ESC / clic droit.
        # (device_removed garde son sens système : on l'ignore ici.)
        if (
            routed_input.action is InputAction.UI_CANCEL
            and routed_input.variant != "device_removed"
        ):
            self.game.scene_manager.pop()
            return MenuAction.BACK
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action is not None and action.startswith("level:"):
            level_id = int(action.partition(":")[2])
            self.game.scene_manager.switch(GameplayScene(self.game, level_id))
        # A locked level reports None: the model refuses it, so nothing happened.
        return action

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        surface.fill(Colors.dark_grey)
        self.view.draw(surface, self.TITLE, self.model, top=180)
        return None
