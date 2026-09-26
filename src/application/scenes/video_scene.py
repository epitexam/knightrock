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
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game


class VideoScene(Scene):
    TITLE = "VIDEO"
    SCALE_VALUES: tuple[float, ...] = (0.8, 1.0, 1.2)
    VALUE_FLASH_SECONDS = 0.5
    # La fenêtre n'est pas redimensionnable : la taille choisie est le viewport
    # logique stable du jeu (culling caméra, budget de streaming). La liste des
    # presets appartient à ``ResolutionScene``, l'écran de sélection ; elle est
    # réexportée ici pour le raccourci ←/→ et l'affichage de la ligne.

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = MenuView(game.settings.ui_scale)
        self._signature = self._current_signature()
        self._flash_row = -1
        self._flash_remaining = 0.0
        self._rebuild()

    def _current_signature(self) -> tuple[int, int, bool, bool, float]:
        """The settings this screen renders, used to skip redundant rebuilds."""
        settings = self.game.settings
        return (
            settings.width,
            settings.height,
            settings.fullscreen,
            settings.vsync,
            settings.ui_scale,
        )

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
        """Tick down the value-change flash."""
        if self._flash_remaining > 0.0:
            self._flash_remaining = max(0.0, self._flash_remaining - delta_time)
            if self._flash_remaining == 0.0:
                self._flash_row = -1

    def _flash_value_change(self) -> None:
        """Mark the focused row as just changed, for ``VALUE_FLASH_SECONDS``.

        Cycling a value with ←/→ changes the label, but the label is also what
        marks the row as selected, so without a distinct colour the player got
        no confirmation that the press landed.
        """
        current = self.model.current_item
        self._flash_row = self.model.current_index if current is not None else -1
        self._flash_remaining = self.VALUE_FLASH_SECONDS if self._flash_row >= 0 else 0.0

    def handle_routed(self, routed: RoutedInput) -> str | None:
        if routed.action in (InputAction.UI_BACK, InputAction.UI_CANCEL):
            if routed.variant != "device_removed":
                self.game.scene_manager.pop()
                return MenuAction.BACK
            return None
        if self._handle_row_value_navigation(routed):
            # ←/→ on a value row, or Enter on the resolution row: the value
            # changed in place, which is a confirmation and not a navigation.
            return MenuAction.ACTIVATE
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
            return MenuAction.BACK
        return action

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
        self._signature = self._current_signature()
        self._flash_value_change()

    def set_ui_scale(self, scale: float) -> None:
        self.view.set_scale(scale)

    def draw(self, surface: pygame.Surface) -> None:
        if self._current_signature() != self._signature:
            self._signature = self._current_signature()
            focused = self.model.current_item.action if self.model.current_item else None
            self._rebuild(focused)
        self.view.draw(
            surface,
            self.TITLE,
            self.model,
            top=150,
            highlighted=self._flash_row,
        )
