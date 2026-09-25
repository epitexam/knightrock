from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import UserSettings
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class OptionsScene(Scene):
    TITLE = "OPTIONS"
    SCALE_VALUES = (0.8, 1.0, 1.2)

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = MenuView(game.settings.ui_scale)
        self._rebuild_items()

    def _rebuild_items(self) -> None:
        settings = self.game.settings
        self.model.set_items(
            (
                MenuItem("scale", f"UI scale: {settings.ui_scale:.1f}x"),
                MenuItem("fullscreen", f"Fullscreen: {'on' if settings.fullscreen else 'off'}"),
                MenuItem("vsync", f"VSync: {'on' if settings.vsync else 'off'}"),
                MenuItem(
                    "invert_y",
                    f"Stick Y: {'inverted' if settings.bindings.menu.invert_y else 'normal'}",
                ),
                MenuItem("controls", "Controls"),
                MenuItem("video", "Video settings"),
                MenuItem("reset", "Reset options"),
                MenuItem("back", "Back"),
            )
        )

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed_input: RoutedInput) -> None:
        if self._is_back(routed_input):
            self.game.scene_manager.pop()
            return
        action, _ = self.model.handle_routed(
            routed_input.action, routed_input.position, self.view.item_rects, routed_input.variant
        )
        self._handle_action(action)

    @staticmethod
    def _is_back(routed_input: RoutedInput) -> bool:
        return routed_input.action is InputAction.UI_BACK or (
            routed_input.action is InputAction.UI_CANCEL
            and routed_input.variant != "device_removed"
        )

    def _handle_action(self, action: str | None) -> None:
        if action == "back":
            self.game.scene_manager.pop()
        elif action == "scale":
            self._cycle_scale()
        elif action == "fullscreen":
            self._apply(replace(self.game.settings, fullscreen=not self.game.settings.fullscreen))
        elif action == "vsync":
            self._apply(replace(self.game.settings, vsync=not self.game.settings.vsync))
        elif action == "invert_y":
            self._toggle_invert_y()
        elif action == "video":
            self.game.scene_manager.push(VideoScene(self.game))
        elif action == "controls":
            from src.application.scenes.controls_category_scene import ControlsCategoryScene

            self.game.scene_manager.push(ControlsCategoryScene(self.game))
        elif action == "reset":
            self._reset()

    def _reset(self) -> None:
        defaults = UserSettings()
        current_bindings = self.game.settings.bindings
        default_menu = defaults.bindings.menu
        self._apply(
            replace(
                self.game.settings,
                ui_scale=defaults.ui_scale,
                fullscreen=defaults.fullscreen,
                vsync=defaults.vsync,
                bindings=replace(
                    current_bindings,
                    menu=replace(current_bindings.menu, invert_y=default_menu.invert_y),
                ),
            )
        )

    def _cycle_scale(self) -> None:
        index = self.SCALE_VALUES.index(self.game.settings.ui_scale)
        self._apply(
            replace(
                self.game.settings,
                ui_scale=self.SCALE_VALUES[(index + 1) % len(self.SCALE_VALUES)],
            )
        )

    def _toggle_invert_y(self) -> None:
        menu = replace(
            self.game.settings.bindings.menu,
            invert_y=not self.game.settings.bindings.menu.invert_y,
        )
        bindings = replace(self.game.settings.bindings, menu=menu)
        self._apply(self.game.settings.with_bindings(bindings))

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is None:
            return None
        self.view.set_scale(self.game.settings.ui_scale)
        self.view.draw(surface, self.TITLE, self.model, top=150)
        return None

    def _apply(self, settings: UserSettings) -> None:
        self.game.apply_settings(settings)
        self._rebuild_items()
