from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.menu_scene import MenuScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.styles import TEXT_WARN

if TYPE_CHECKING:
    from src.core.game import Game


class PauseScene(Scene):
    TITLE = "PAUSE"

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(game)
        self.level_id = level_id
        items = (MenuItem("resume", "Resume"), MenuItem("menu", "Back to menu"))
        self.OPTIONS = tuple(item.label for item in items)
        self.model = MenuModel(items)
        self.view = MenuView()

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if routed_input.action is InputAction.UI_BACK:
            self.game.scene_manager.pop()
            return
        if (
            routed_input.action is InputAction.UI_CANCEL
            and routed_input.variant != "device_removed"
        ):
            self.game.scene_manager.switch(MenuScene(self.game))
            return
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "resume":
            self.game.scene_manager.pop()
        elif action == "menu":
            self.game.scene_manager.switch(MenuScene(self.game))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((8, 10, 14, 190))
        surface.blit(overlay, (0, 0))
        self.view.draw(surface, self.TITLE, self.model, top=220, title_color=TEXT_WARN)
        return None
