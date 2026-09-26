"""Options hub: a category menu over the dedicated settings screens.

Every actual setting lives in the screen that owns it, so a value has a
single source of truth and a single place to change it:

- **Video settings** — resolution, fullscreen, VSync, UI scale;
- **Controls** — key/button rebinding and the menu stick Y inversion.

This screen is navigation only: it holds no toggle of its own, hence no
"reset" here either. Each sub-menu resets exactly what it owns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class OptionsScene(Scene):
    TITLE = "OPTIONS"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel(
            (
                MenuItem("video", "Video settings"),
                MenuItem("controls", "Controls"),
                MenuItem("back", "Back"),
            )
        )
        self.view = MenuView(game.settings.ui_scale)

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if routed_input.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            if routed_input.variant != "device_removed":
                self.game.scene_manager.pop()
                return MenuAction.BACK
            return None
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "video":
            from src.application.scenes.video_scene import VideoScene

            self.game.scene_manager.push(VideoScene(self.game))
        elif action == "controls":
            from src.application.scenes.controls_category_scene import ControlsCategoryScene

            self.game.scene_manager.push(ControlsCategoryScene(self.game))
        elif action == "back":
            self.game.scene_manager.pop()
            return MenuAction.BACK
        return action

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        self.view.set_scale(self.game.settings.ui_scale)
        self.view.draw(surface, self.TITLE, self.model, top=220)
        return None
