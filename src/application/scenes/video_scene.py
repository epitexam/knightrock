"""Video settings: how to occupy the screen, and how it is presented.

Sole owner of the display settings. They used to be duplicated in the Options
hub, which let the player change the same value from two places; the Options
screen is now navigation only.

There is no resolution row, and that is the point rather than an omission. A
list of window sizes is a claim about the player's monitor that the game cannot
check -- offering 2560x1440 to a 1366x768 laptop is what that costs -- and a
remembered size is a claim that goes stale: in borderless the window is the
desktop's size whatever the file says, and the row would go on displaying a
number the game was not using. The window is now the only source of truth, the
player resizes it with the window manager, and the picture follows. So every row
here is something the game can actually honour: a mode, whole-pixel art, a
refresh, a cadence, a text size.
"""

from typing import TYPE_CHECKING

import pygame

from src.application.scene import Scene
from src.application.settings_store import FRAME_LIMITS, UI_SCALES, UserSettings
from src.core.display.detection import desktop_refresh_rates
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import fits_whole_pixel, letterbox
from src.core.display.mode import DisplayMode
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

if TYPE_CHECKING:
    from src.core.game import Game

#: The modes offered as a cycle, ``AUTO`` first: it is a real choice -- "decide
#: again next launch, on whatever machine I am on" -- and the row shows what it
#: resolves to until the player picks something else.
DISPLAY_VALUES = (
    DisplayMode.AUTO,
    DisplayMode.BORDERLESS,
    DisplayMode.WINDOW,
    DisplayMode.FULLSCREEN,
)


class VideoScene(Scene):
    TITLE = "VIDEO"
    SCALE_VALUES: tuple[float, ...] = UI_SCALES
    VALUE_FLASH_SECONDS = 0.5
    FOOTER = "↑↓ row · ←→ change · Esc back"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view = MenuView(game.ui_scale)
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
            settings.pixel_perfect,
            settings.vsync,
            settings.frame_limit,
            settings.ui_scale,
            self._screen_refresh_rate(),
            self._window_size(),
        )

    def _rebuild(self, selected_action: str | None = None) -> None:
        settings = self.game.settings
        items = (
            MenuItem("display", "Display", self._display_label()),
            MenuItem(
                "pixel_perfect",
                "Whole-pixel art",
                self._pixel_perfect_label(),
                fits_whole_pixel(self._window_size(), DEFAULT_FRAMING),
            ),
            MenuItem("vsync", "VSync", self._vsync_label()),
            MenuItem("frame_limit", "Frame limit", self._frame_limit_label()),
            MenuItem("scale", "UI scale", f"{settings.ui_scale:.1f}x"),
            MenuItem(
                "frame_counter", "Frame timings", self._on_off(settings.frame_counter)
            ),
            MenuItem("reset", "Reset video settings"),
            MenuItem("back", "Back"),
            MenuItem("info", "Window", self._window_label(), enabled=False),
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

    def _window_size(self) -> tuple[int, int]:
        """The window the picture is actually in.

        Read off the presentation rather than the stage, because the
        presentation's surface *is* the window surface the frame is blitted onto,
        so this is the size the reported density is about. With no window yet --
        a headless run, a test -- the framing's own size is the honest answer,
        and the density it implies is exactly 1.
        """
        if self.game.presentation is not None:
            return self.game.presentation.window_size
        if self.game.stage is not None:
            return self.game.stage.size
        return (round(DEFAULT_FRAMING.width), round(DEFAULT_FRAMING.height))

    def _window_label(self) -> str:
        """What the game derived from the window, so the player can see it.

        The information the resolution row used to withhold by showing a number
        the game was not using. Two facts, both derived and neither stored: how
        big the picture is inside the window, and how many pixels a world unit
        gets there.
        """
        size = self._window_size()
        rect = letterbox(size, DEFAULT_FRAMING, pixel_perfect=self.game.settings.pixel_perfect)
        bars = "" if rect.size == tuple(size) else " + bars"
        return f"{rect.width}x{rect.height} at {rect.width / DEFAULT_FRAMING.width:.2f}x{bars}"

    def _pixel_perfect_label(self) -> str:
        """The whole-pixel row, which has to be able to say "not here"."""
        if not fits_whole_pixel(self._window_size(), DEFAULT_FRAMING):
            return "off (window too small)"
        return self._on_off(self.game.settings.pixel_perfect)

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
        if action in self.CYCLING_ROWS:
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
    #: screen is named in :meth:`handle_routed` (``reset``, ``back``) or is not
    #: an action at all (``info``, which only reports). A row in neither set is a
    #: row that does nothing, and this list is the check that there is no such
    #: row: ``test_every_row_does_something`` reads it against the real model.
    CYCLING_ROWS = (
        "display",
        "pixel_perfect",
        "vsync",
        "frame_limit",
        "scale",
        "frame_counter",
    )

    def _handle_row_value_navigation(self, routed: RoutedInput) -> bool:
        """←/→ adjust the focused row's value, and Enter does the same.

        Every value row acts on all three, so a gamepad never lands on a row it
        cannot use.

        A row that is *not* usable -- the whole-pixel art on a window too small
        to hold one, the window read-out -- swallows the press instead of
        passing it on. The alternative was worse than a dead key: the menu model
        answers an action on a disabled row by activating the nearest enabled
        one, so Enter on the read-out line silently changed the display mode. A
        row that cannot be used has to do nothing, visibly.
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
            "pixel_perfect": lambda: self._cycle_bool(action, "pixel_perfect", click=click),
            "vsync": lambda: self._cycle_bool(action, "vsync", click=click),
            "frame_limit": lambda: self._cycle_frame_limit(action),
            "scale": lambda: self._cycle_scale(action),
            "frame_counter": lambda: self._cycle_bool(
                action, "frame_counter", click=click
            ),
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

    def _cycle_scale(self, action: InputAction) -> None:
        current = self.game.settings.ui_scale
        index = self.SCALE_VALUES.index(current) if current in self.SCALE_VALUES else 1
        step = -1 if action is InputAction.UI_LEFT else 1
        size = len(self.SCALE_VALUES)
        self._apply(
            self.game.settings.with_video(ui_scale=self.SCALE_VALUES[(index + step) % size])
        )

    def _reset(self) -> None:
        """Put every video setting back to its default, and only those.

        The bindings are carried over untouched: this is the video screen, and
        a player who resets it should not lose the controls they just rebound.
        """
        defaults = UserSettings()
        self._apply(
            self.game.settings.with_video(
                display=defaults.display,
                pixel_perfect=defaults.pixel_perfect,
                vsync=defaults.vsync,
                frame_limit=defaults.frame_limit,
                ui_scale=defaults.ui_scale,
                frame_counter=defaults.frame_counter,
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
        self.view.set_scale(self.game.ui_scale)
        self.view.draw(
            surface,
            self.TITLE,
            self.model,
            top=150,
            highlighted=self._flash_row,
            footers=(self.FOOTER,),
        )


def detection_resolution(scene: VideoScene) -> str:
    """What AUTO resolves to on this machine, for the row that has not been decided.

    Read from the platform rather than remembered, which is the difference
    between a label that is right and one that is right until the player moves
    the window to another screen.
    """
    from src.core.display.detection import auto_display_mode, desktop_size

    return auto_display_mode(DEFAULT_FRAMING, desktop_size()).value
