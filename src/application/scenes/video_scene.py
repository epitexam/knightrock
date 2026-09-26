"""Video settings: display mode, window size, sharpness, vsync, frame limit.

Sole owner of the display settings. They used to be duplicated in the Options
hub, which let the player change the same value from two places; the Options
screen is now navigation only.

Every row here is either a decision the machine cannot make for you (the
sharpness and pacing rows) or a decision it can and does (the display mode and
the window size, which resolve themselves against the desktop on every launch).
The two size rows are the ones worth reading twice: a fixed list of absolute
resolutions is a claim about the player's monitor that the game has no way to
check, and offering 2560x1440 to a 1366x768 laptop is what that costs.
"""

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.scenes.resolution_scene import ResolutionScene
from src.application.settings_store import FRAME_LIMITS, UserSettings
from src.core.display.detection import desktop_refresh_rates, desktop_size
from src.core.display.mode import DisplayMode
from src.core.display.size_mode import SizeMode
from src.core.display.viewport import RENDER_SCALES
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game

#: The modes offered as a cycle, skipping AUTO: that is the absence of a
#: decision, and the row shows its resolved value until the player picks one.
DISPLAY_VALUES = (DisplayMode.BORDERLESS, DisplayMode.WINDOW, DisplayMode.FULLSCREEN)

#: Scale a player is told about when their window is too big for the default
#: sharpness. Measured in tests/benchmarks/render_benchmark.py.
COST_WARNING_THRESHOLD_PX = 2560


class VideoScene(Scene):
    TITLE = "VIDEO"
    SCALE_VALUES: tuple[float, ...] = (0.8, 1.0, 1.2)
    VALUE_FLASH_SECONDS = 0.5
    FOOTER = "↑↓ row · ←→ change · Enter window size · Esc back"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = MenuView(game.settings.ui_scale)
        self._signature = self._current_signature()
        self._flash_row = -1
        self._flash_remaining = 0.0
        self._rebuild()

    # ------------------------------------------------------------------ rows

    def _current_signature(self) -> tuple[object, ...]:
        """The settings this screen renders, used to skip redundant rebuilds."""
        settings = self.game.settings
        return (
            settings.display,
            settings.width,
            settings.height,
            settings.size_mode,
            settings.render_scale,
            settings.smoothing,
            settings.vsync,
            settings.frame_limit,
            settings.ui_scale,
            self._screen_refresh_rate(),
        )

    def _rebuild(self, selected_action: str | None = None) -> None:
        settings = self.game.settings
        items = (
            MenuItem("display", "Display", self._display_label()),
            MenuItem(
                "size",
                "Window size",
                self._size_label(),
                settings.display is not DisplayMode.BORDERLESS,
            ),
            MenuItem("render_scale", "Render scale", _render_scale_label(settings.render_scale)),
            MenuItem("smoothing", "Smooth scaling", self._on_off(settings.smoothing)),
            MenuItem("vsync", "VSync", self._vsync_label()),
            MenuItem("frame_limit", "Frame limit", self._frame_limit_label()),
            MenuItem("scale", "UI scale", f"{settings.ui_scale:.1f}x"),
            MenuItem("reset", "Reset video settings"),
            MenuItem("back", "Back"),
        )
        selected = next(
            (index for index, item in enumerate(items) if item.action == selected_action), 0
        )
        self.model.set_items(items, selected)

    def _display_label(self) -> str:
        mode = self.game.settings.display
        if mode is DisplayMode.AUTO:
            return f"auto ({detection_resolution(self)})"
        return mode.value

    def _size_label(self) -> str:
        settings = self.game.settings
        size = f"{settings.width} x {settings.height}"
        if settings.size_mode is SizeMode.AUTO:
            return f"{size} (auto)"
        return size

    def _vsync_label(self) -> str:
        rate = self._screen_refresh_rate()
        suffix = f" {rate} Hz screen" if rate else ""
        if self.game.settings.vsync and not self._vsync_is_active():
            # The driver did not honour the request. Saying so is the whole
            # point of checking: the setting looks alive either way, and the
            # only symptom otherwise is a frame rate that never settles.
            return f"off (unavailable){suffix}"
        return f"{self._on_off(self.game.settings.vsync)}{suffix}"

    def _frame_limit_label(self) -> str:
        limit = self.game.settings.frame_limit
        return "Uncapped" if limit is None else str(limit)

    @staticmethod
    def _on_off(value: bool) -> str:
        return "on" if value else "off"

    @staticmethod
    def _screen_refresh_rate() -> int:
        rates = desktop_refresh_rates()
        return rates[0] if rates else 0

    def _vsync_is_active(self) -> bool:
        try:
            return bool(pygame.display.is_vsync())
        except pygame.error:
            return False

    # --------------------------------------------------------------- cycling

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
            return MenuAction.ACTIVATE
        action, _ = self.model.handle_routed(
            routed.action, routed.position, self.view.item_rects, routed.variant
        )
        if action == "size":
            self._open_size_picker()
        elif action in self.CYCLING_ROWS:
            # A click on a value row steps it forward, the same as →.
            #
            # It used to do nothing, which is the same as a dead row: the focus
            # moved, so the click *looked* like it had landed, and the value
            # only changed if you then pressed a direction or Enter. Six of the
            # nine rows were dead to the mouse that way, and the only ones that
            # worked were the three handled by name below -- which is a bug that
            # reads as "this menu is awkward" rather than as a bug, because a
            # row that highlights on click looks alive.
            self._cycle(action, InputAction.UI_RIGHT, click=True)
        elif action == "reset":
            self._reset()
        elif action == "back":
            self.game.scene_manager.pop()
            return MenuAction.BACK
        return action

    #: Rows whose value a press -- or a click -- steps. Every other row on this
    #: screen is an action of its own (``size``, ``reset``, ``back``), named in
    #: :meth:`handle_routed`. A row in neither set is a row that does nothing,
    #: and the list is the check that there is no such row.
    CYCLING_ROWS = ("display", "render_scale", "smoothing", "vsync", "frame_limit", "scale")

    def _handle_row_value_navigation(self, routed: RoutedInput) -> bool:
        """←/→ adjust the focused row's value; Enter opens the real picker.

        Every value row acts on all three, so a gamepad never lands on a row it
        cannot use.
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
        if not current.enabled:
            return False
        if current.action == "size":
            if routed.action is InputAction.UI_CONFIRM:
                self._open_size_picker()
            else:
                self._cycle_size(routed.action)
            return True
        return self._cycle(current.action, routed.action)

    def _cycle(self, name: str, action: InputAction, *, click: bool = False) -> bool:
        """Step one row's value: forwards on a click and on →, back on ←.

        One implementation for both paths, deliberately. The two used to be
        separate lists naming the same rows, which is exactly how a click ended
        up wired to three of them and a key to six. A row the pointer cannot
        reach is a row the pointer cannot use.
        """
        cyclers = {
            "display": lambda: self._cycle_enum(action, DISPLAY_VALUES, "display"),
            "render_scale": lambda: self._cycle_enum(action, RENDER_SCALES, "render_scale"),
            "smoothing": lambda: self._cycle_bool(action, "smoothing", click=click),
            "vsync": lambda: self._cycle_bool(action, "vsync", click=click),
            "frame_limit": lambda: self._cycle_frame_limit(action),
            "scale": lambda: self._cycle_scale(action),
        }
        cycler = cyclers.get(name)
        if cycler is None:
            return False
        cycler()
        return True

    def _cycle_enum(self, action: InputAction, values: tuple, name: str) -> None:
        current = getattr(self.game.settings, name)
        index = values.index(current) if current in values else 0
        step = -1 if action is InputAction.UI_LEFT else 1
        self._apply(self.game.settings.with_video(**{name: values[(index + step) % len(values)]}))

    def _cycle_bool(self, action: InputAction, name: str, *, click: bool = False) -> None:
        # A left/right press sets the value rather than toggling it: toggling
        # makes ← and → behave identically, which reads as one of them broken.
        #
        # A click is not that. It is one discrete gesture with no direction to
        # read a value out of, so on a row that already reads "on" it has to
        # flip. Setting it instead made the row answer half the time, which is
        # the same as a row that reads as dead -- and the two together are what
        # made the screen look broken rather than merely terse.
        value = not getattr(self.game.settings, name) if click else action is InputAction.UI_RIGHT
        self._apply(self.game.settings.with_video(**{name: value}))

    def _cycle_frame_limit(self, action: InputAction) -> None:
        current = self.game.settings.frame_limit
        index = FRAME_LIMITS.index(current) if current in FRAME_LIMITS else 0
        step = -1 if action is InputAction.UI_LEFT else 1
        self._apply(
            self.game.settings.with_video(
                frame_limit=FRAME_LIMITS[(index + step) % len(FRAME_LIMITS)]
            )
        )

    def _cycle_size(self, action: InputAction) -> None:
        from src.core.display.detection import window_size_choices

        choices = window_size_choices(desktop_size())
        if not choices:
            return
        current = (self.game.settings.width, self.game.settings.height)
        index = choices.index(current) if current in choices else 0
        step = -1 if action is InputAction.UI_LEFT else 1
        width, height = choices[(index + step) % len(choices)]
        self._apply(
            self.game.settings.with_video(width=width, height=height, size_mode=SizeMode.MANUAL)
        )

    def _cycle_scale(self, action: InputAction) -> None:
        current = self.game.settings.ui_scale
        index = self.SCALE_VALUES.index(current) if current in self.SCALE_VALUES else 1
        step = -1 if action is InputAction.UI_LEFT else 1
        self._apply(self.game.settings.with_video(ui_scale=self.SCALE_VALUES[(index + step) % 3]))

    def _open_size_picker(self) -> None:
        self.game.scene_manager.push(ResolutionScene(self.game))

    def _reset(self) -> None:
        defaults = UserSettings()
        self._apply(
            self.game.settings.with_video(
                display=defaults.display,
                width=defaults.width,
                height=defaults.height,
                size_mode=defaults.size_mode,
                render_scale=defaults.render_scale,
                smoothing=defaults.smoothing,
                vsync=defaults.vsync,
                frame_limit=defaults.frame_limit,
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

    def _cost_hint(self) -> str:
        """Tell the player when their window is too big for the default sharpness.

        Measured in ``tests/benchmarks/render_benchmark.py``: smooth scaling
        plus a 2x world draw is 70% of a 60Hz frame at 2560x1440 and 105% at
        3840x2160, so on a large display one of the two rows above has to give.
        Saying so is cheaper than a stutter they cannot explain.
        """
        window = self.game.stage.size if self.game.stage is not None else (0, 0)
        if window[0] < COST_WARNING_THRESHOLD_PX:
            return ""
        scale = self.game.settings.render_scale
        if scale is None or scale <= 1 or not self.game.settings.smoothing:
            return ""
        return "Large window: consider Render scale 1x or Smooth scaling off"

    def draw(self, surface: pygame.Surface) -> None:
        if self._current_signature() != self._signature:
            self._signature = self._current_signature()
            focused = self.model.current_item.action if self.model.current_item else None
            self._rebuild(focused)
        self.view.set_scale(self.game.settings.ui_scale)
        self.view.draw(
            surface,
            self.TITLE,
            self.model,
            top=150,
            highlighted=self._flash_row,
            footers=(self.FOOTER, self._cost_hint()),
        )


def _render_scale_label(scale: int | None) -> str:
    """The sharpness the target is drawn at, in the player's own terms.

    ``None`` only survives until the window exists -- the launch resolves it and
    writes it back -- so this is the honest answer for a screen the game has not
    sized yet, rather than a number that would be about to change.
    """
    return f"{scale}x" if scale is not None else "auto"


def detection_resolution(scene: VideoScene) -> str:
    """What AUTO resolved to, for the row that has not been decided yet."""
    from src.core.display.detection import auto_display_mode
    from src.core.display.framing import DEFAULT_FRAMING

    return auto_display_mode(DEFAULT_FRAMING, desktop_size()).value
