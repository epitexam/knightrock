"""Video settings: window size, fullscreen and VSync."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.settings_store import (
    MAX_WINDOW_HEIGHT,
    MAX_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    UserSettings,
)
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class VideoScene(Scene):
    TITLE = "VIDEO"
    WIDTH_STEP = 160
    HEIGHT_STEP = 90

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = MenuView(game.settings.ui_scale)
        self._rebuild()

    def _rebuild(self) -> None:
        settings = self.game.settings
        self.model.set_items(
            (
                MenuItem("width", f"Window width: {settings.width}"),
                MenuItem("height", f"Window height: {settings.height}"),
                MenuItem("fullscreen", f"Fullscreen: {'on' if settings.fullscreen else 'off'}"),
                MenuItem("vsync", f"VSync: {'on' if settings.vsync else 'off'}"),
                MenuItem("back", "Back"),
            )
        )

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed: RoutedInput) -> None:
        if routed.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            if routed.variant != "device_removed":
                self.game.scene_manager.pop()
            return
        if routed.action in (InputAction.UI_LEFT, InputAction.UI_RIGHT):
            self._adjust_dimension(routed.action)
            return
        action, _ = self.model.handle_routed(
            routed.action, routed.position, self.view.item_rects, routed.variant
        )
        if action == "width":
            self._apply(
                replace(
                    self.game.settings,
                    width=self._bounded(
                        self.game.settings.width + self.WIDTH_STEP,
                        MIN_WINDOW_WIDTH,
                        MAX_WINDOW_WIDTH,
                    ),
                )
            )
        elif action == "height":
            self._apply(
                replace(
                    self.game.settings,
                    height=self._bounded(
                        self.game.settings.height + self.HEIGHT_STEP,
                        MIN_WINDOW_HEIGHT,
                        MAX_WINDOW_HEIGHT,
                    ),
                )
            )
        elif action == "fullscreen":
            self._apply(replace(self.game.settings, fullscreen=not self.game.settings.fullscreen))
        elif action == "vsync":
            self._apply(replace(self.game.settings, vsync=not self.game.settings.vsync))
        elif action == "back":
            self.game.scene_manager.pop()

    def _adjust_dimension(self, action: InputAction) -> None:
        current = self.model.current_item
        if current is None:
            return
        direction = -1 if action is InputAction.UI_LEFT else 1
        if current.action == "width":
            self._apply(
                replace(
                    self.game.settings,
                    width=self._bounded(
                        self.game.settings.width + direction * self.WIDTH_STEP,
                        MIN_WINDOW_WIDTH,
                        MAX_WINDOW_WIDTH,
                    ),
                )
            )
        elif current.action == "height":
            self._apply(
                replace(
                    self.game.settings,
                    height=self._bounded(
                        self.game.settings.height + direction * self.HEIGHT_STEP,
                        MIN_WINDOW_HEIGHT,
                        MAX_WINDOW_HEIGHT,
                    ),
                )
            )

    @staticmethod
    def _bounded(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, value))

    def _apply(self, settings: UserSettings) -> None:
        self.game.apply_settings(settings)
        self._rebuild()

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is not None:
            self.view.draw(surface, self.TITLE, self.model, top=150)
        return None
