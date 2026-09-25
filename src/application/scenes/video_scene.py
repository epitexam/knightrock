"""Video settings: window size, fullscreen and VSync."""

from dataclasses import replace
from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.settings_store import UserSettings
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class VideoScene(Scene):
    TITLE = "VIDEO"
    # Résolutions proposées dans le menu vidéo. Une taille choisie ici est
    # toujours un couple cohérent ; le redimensionnement manuel reste possible
    # mais n'est pas proposé comme une option de configuration.
    RESOLUTIONS: tuple[tuple[int, int], ...] = (
        (1024, 576),
        (1280, 720),
        (1366, 768),
        (1440, 900),
        (1600, 900),
        (1920, 1080),
        (2560, 1440),
    )

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = MenuView(game.settings.ui_scale)
        self._rebuild()

    def _rebuild(self, selected_action: str | None = None) -> None:
        settings = self.game.settings
        resolution = self._resolution_label(settings.width, settings.height)
        items = (
            MenuItem("resolution", f"Resolution: {resolution}"),
            MenuItem("fullscreen", f"Fullscreen: {'on' if settings.fullscreen else 'off'}"),
            MenuItem("vsync", f"VSync: {'on' if settings.vsync else 'off'}"),
            MenuItem("reset", "Reset video settings"),
            MenuItem("back", "Back"),
        )
        selected = next(
            (index for index, item in enumerate(items) if item.action == selected_action), 0
        )
        self.model.set_items(items, selected)

    def update(self, delta_time: float) -> None:
        return None

    def handle_routed(self, routed: RoutedInput) -> None:
        if routed.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            if routed.variant != "device_removed":
                self.game.scene_manager.pop()
            return
        if self._handle_resolution_navigation(routed):
            return
        action, _ = self.model.handle_routed(
            routed.action, routed.position, self.view.item_rects, routed.variant
        )
        if action == "resolution":
            self._cycle_resolution()
        elif action == "fullscreen":
            self._apply(replace(self.game.settings, fullscreen=not self.game.settings.fullscreen))
        elif action == "vsync":
            self._apply(replace(self.game.settings, vsync=not self.game.settings.vsync))
        elif action == "reset":
            self._reset()
        elif action == "back":
            self.game.scene_manager.pop()

    def _handle_resolution_navigation(self, routed: RoutedInput) -> bool:
        current = self.model.current_item
        if current is None:
            return False
        if routed.action in (InputAction.UI_LEFT, InputAction.UI_RIGHT):
            if current.action == "resolution":
                self._cycle_resolution(routed.action)
                return True
            return False
        if routed.action is InputAction.UI_CONFIRM and current.action == "resolution":
            self._cycle_resolution()
            return True
        return False

    def _cycle_resolution(self, action: InputAction = InputAction.UI_CONFIRM) -> None:
        current = (self.game.settings.width, self.game.settings.height)
        index = self.RESOLUTIONS.index(current) if current in self.RESOLUTIONS else 0
        direction = -1 if action is InputAction.UI_LEFT else 1
        width, height = self.RESOLUTIONS[(index + direction) % len(self.RESOLUTIONS)]
        self._apply(replace(self.game.settings, width=width, height=height))

    @staticmethod
    def _resolution_label(width: int, height: int) -> str:
        return f"{width} x {height}" if (width, height) in VideoScene.RESOLUTIONS else "custom"

    def _reset(self) -> None:
        defaults = UserSettings()
        self._apply(
            replace(
                self.game.settings,
                width=defaults.width,
                height=defaults.height,
                fullscreen=defaults.fullscreen,
                vsync=defaults.vsync,
            )
        )

    def _apply(self, settings: UserSettings) -> None:
        selected_action = self.model.current_item.action if self.model.current_item else None
        self.game.apply_settings(settings)
        self._rebuild(selected_action)

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)

    def draw(self) -> list[pygame.Rect] | None:
        surface = pygame.display.get_surface()
        if surface is not None:
            self.view.draw(surface, self.TITLE, self.model, top=150)
        return None
