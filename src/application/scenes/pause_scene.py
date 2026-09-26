from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.menu_scene import MenuScene
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView
from src.ui.styles import TEXT_WARN

if TYPE_CHECKING:
    from src.core.game import Game


class PauseScene(Scene):
    TITLE = "PAUSE"

    #: The world stops; see ``Scene.halts_simulation`` for why saying so
    #: is not the same as simply not updating.
    halts_simulation = True

    def __init__(self, game: Game, level_id: int = 0) -> None:
        super().__init__(game)
        self.level_id = level_id
        items = (
            MenuItem("resume", "Resume"),
            MenuItem("options", "Options"),
            MenuItem("menu", "Back to menu"),
        )
        self.OPTIONS = tuple(item.label for item in items)
        self.model = MenuModel(items)
        self.view = MenuView()
        self._overlay: pygame.Surface | None = None
        self._overlay_size: tuple[int, int] = (0, 0)
        self._overlay_color: tuple[int, int, int, int] = (8, 10, 14, 190)

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> str | None:
        if routed_input.action is InputAction.UI_BACK:
            self.game.scene_manager.pop()
            return MenuAction.BACK
        if (
            routed_input.action is InputAction.UI_CANCEL
            and routed_input.variant != "device_removed"
        ):
            self.game.scene_manager.switch(MenuScene(self.game))
            return MenuAction.BACK
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        if action == "resume":
            self.game.scene_manager.pop()
        elif action == "menu":
            self.game.scene_manager.switch(MenuScene(self.game))
        elif action == "options":
            from src.application.scenes.options_scene import OptionsScene

            self.game.scene_manager.push(OptionsScene(self.game))
        return action

    def draw(self, surface: pygame.Surface) -> None:
        size = surface.get_size()
        if self._overlay is None or self._overlay_size != size:
            self._overlay = pygame.Surface(size, pygame.SRCALPHA)
            self._overlay_size = size
            self._overlay.fill(self._overlay_color)
        surface.blit(self._overlay, (0, 0))
        self.view.draw(surface, self.TITLE, self.model, top=220, title_color=TEXT_WARN)
