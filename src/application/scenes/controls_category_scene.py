"""Category menu for the two control-mapping screens."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.controls_scene import ControlsScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class ControlsCategoryScene(Scene):
    TITLE = "CONTROLS"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel(
            (
                MenuItem("menu", "Menu controls"),
                MenuItem("gameplay", "Gameplay controls"),
                MenuItem("back", "Back"),
            )
        )
        self.view = MenuView(game.settings.ui_scale)

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if routed_input.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            if routed_input.variant != "device_removed":
                self.game.scene_manager.pop()
            return
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "menu":
            self.game.scene_manager.push(ControlsScene(self.game, ControlsScene.MENU_SECTION))
        elif action == "gameplay":
            self.game.scene_manager.push(ControlsScene(self.game, ControlsScene.GAMEPLAY_SECTION))
        elif action == "back":
            self.game.scene_manager.pop()

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        self.view.set_scale(self.game.settings.ui_scale)
        self.view.draw(surface, self.TITLE, self.model, top=220)
        return None
