"""Video settings: resolution, window mode, VSync and UI scale.

Sole owner of the display settings. They used to be duplicated in the
Options hub, which let the player change the same value from two places; the
Options screen is now navigation only.
"""

from dataclasses import replace
from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.resolution_scene import RESOLUTIONS
from src.application.settings_store import UserSettings
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class VideoScene(Scene):
    TITLE = "VIDEO"
    SCALE_VALUES: tuple[float, ...] = (0.8, 1.0, 1.2)
    # La fenêtre n'est pas redimensionnable : la taille choisie est le viewport
    # logique stable du jeu (culling caméra, budget de streaming). La liste des
    # presets appartient à ``ResolutionScene``, l'écran de sélection ; elle est
    # réexportée ici pour le raccourci ←/→ et l'affichage de la ligne.

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
            MenuItem("scale", f"UI scale: {settings.ui_scale:.1f}x"),
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
        if self._handle_row_value_navigation(routed):
            return
        action, _ = self.model.handle_routed(
            routed.action, routed.position, self.view.item_rects, routed.variant
        )
        if action == "resolution":
            self._open_resolution_picker()
        elif action in ("fullscreen", "vsync"):
            self._toggle(action)
        elif action == "scale":
            self._cycle_scale()
        elif action == "reset":
            self._reset()
        elif action == "back":
            self.game.scene_manager.pop()

    def _handle_row_value_navigation(self, routed: RoutedInput) -> bool:
        """←/→ adjust the focused row's value; Enter opens the real picker.

        Resolution is a list, not a value: ←/→ keep a quick inline nudge but
        Enter opens the dedicated screen where every option is visible. The
        other rows (scale, fullscreen, vsync) cycle on all three, so a gamepad
        never lands on a row it cannot act on.
        """
        current = self.model.current_item
        if current is None:
            return False
        if routed.action not in (
            InputAction.UI_LEFT,
            InputAction.UI_RIGHT,
            InputAction.UI_CONFIRM,
        ):
            return False
        if current.action == "resolution":
            # ←/→ keep the quick inline nudge; Enter opens the real picker.
            if routed.action is InputAction.UI_CONFIRM:
                self._open_resolution_picker()
            else:
                self._cycle_resolution(routed.action)
            return True
        if current.action == "scale":
            self._cycle_scale(routed.action)
            return True
        if (
            current.action in ("fullscreen", "vsync")
            and routed.action is not InputAction.UI_CONFIRM
        ):
            self._toggle(str(current.action))
            return True
        return False

    def _toggle(self, action: str) -> None:
        if action == "fullscreen":
            self._apply(replace(self.game.settings, fullscreen=not self.game.settings.fullscreen))
        else:
            self._apply(replace(self.game.settings, vsync=not self.game.settings.vsync))

    def _open_resolution_picker(self) -> None:
        from src.application.scenes.resolution_scene import ResolutionScene

        self.game.scene_manager.push(ResolutionScene(self.game))

    def _cycle_resolution(self, action: InputAction = InputAction.UI_CONFIRM) -> None:
        current = (self.game.settings.width, self.game.settings.height)
        index = RESOLUTIONS.index(current) if current in RESOLUTIONS else 0
        direction = -1 if action is InputAction.UI_LEFT else 1
        width, height = RESOLUTIONS[(index + direction) % len(RESOLUTIONS)]
        self._apply(replace(self.game.settings, width=width, height=height))

    def _cycle_scale(self, action: InputAction = InputAction.UI_CONFIRM) -> None:
        current = self.game.settings.ui_scale
        index = self.SCALE_VALUES.index(current) if current in self.SCALE_VALUES else 1
        direction = -1 if action is InputAction.UI_LEFT else 1
        scale = self.SCALE_VALUES[(index + direction) % len(self.SCALE_VALUES)]
        self._apply(replace(self.game.settings, ui_scale=scale))

    @staticmethod
    def _resolution_label(width: int, height: int) -> str:
        return f"{width} x {height}" if (width, height) in RESOLUTIONS else "custom"

    def _reset(self) -> None:
        defaults = UserSettings()
        self._apply(
            replace(
                self.game.settings,
                width=defaults.width,
                height=defaults.height,
                fullscreen=defaults.fullscreen,
                vsync=defaults.vsync,
                ui_scale=defaults.ui_scale,
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
            # The resolution can change under this screen (the picker is pushed
            # on top and pops back), and ``pop()`` does not re-enter the scene
            # below, so the labels are refreshed from the live settings here.
            # The focused action is carried over: rebuilding with no selection
            # would snap the cursor back to the first row on every frame.
            focused = self.model.current_item.action if self.model.current_item else None
            self._rebuild(focused)
            self.view.set_scale(self.game.settings.ui_scale)
            self.view.draw(surface, self.TITLE, self.model, top=150)
        return None
