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
        levels = tuple(
            MenuItem(
                f"level:{level_id}",
                f"Level {level_id}",
                enabled=level_id in unlocked,
            )
            for level_id in sorted(game.level_manager.level_paths)
        )
        # A row, not just a key: the keyboard shortcut existed and the pointer
        # had nothing to click. Every other menu here offers both, and a screen
        # reachable only with a keyboard is a screen a controller or a mouse
        # cannot leave.
        self.model = MenuModel((*levels, MenuItem("back", "Back")))
        self.view: MenuView = MenuView(game.ui_scale)

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if routed_input.action is InputAction.UI_BACK:
            self.game.scene_manager.pop()
            return MenuAction.BACK
        # B button (gamepad) = back, same as ESC / right click.
        # (device_removed keeps its system meaning: ignored here.)
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
        elif action == "back":
            self.game.scene_manager.pop()
            return MenuAction.BACK
        # A locked level reports None: the model refuses it, so nothing happened.
        return action

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(Colors.dark_grey)
        self.view.set_scale(self.game.ui_scale)
        self.view.draw(surface, self.TITLE, self.model, top=180)
