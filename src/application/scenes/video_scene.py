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
from src.application.settings_store import (
    FRAME_LIMITS,
    PANEL_SCALES,
    UI_SCALES,
    UserSettings,
)
from src.core.display.detection import desktop_refresh_rates
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import (
    FitPolicy,
    already_a_whole_multiple,
    fits_whole_pixel,
    letterbox,
)
from src.core.display.mode import DisplayMode
from src.core.display.monitors import Resolution, ResolutionReason, Topology
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.core.settings import Debug
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

#: The fit policies, in the order the row steps through them. Bars first because
#: it is the only one that is never surprising, and zoom last because it is the
#: one that costs the player some of the picture.
FIT_POLICIES = (FitPolicy.BARS, FitPolicy.INTEGER, FitPolicy.ZOOM)


class VideoScene(Scene):
    TITLE = "VIDEO"
    SCALE_VALUES: tuple[float, ...] = UI_SCALES
    PANEL_SCALE_VALUES: tuple[float, ...] = PANEL_SCALES
    VALUE_FLASH_SECONDS = 0.5
    FOOTER = "↑↓ row · ←→ change · Esc back"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.model = MenuModel()
        self.view: MenuView = MenuView(game.ui_scale)
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
            settings.panel_scale,
            settings.fit,
            settings.monitor,
            settings.fullscreen_mode,
            # The debug row is conditional on this, and the rebuild is skipped
            # when the signature is unchanged -- so without the flag in the
            # signature, flipping DEBUG mid-session would leave the menu
            # describing a set of rows the model does not have.
            Debug.is_enabled(),
            self._screen_refresh_rate(),
            self._window_size(),
            # The monitor rows are conditional on how many displays exist, and so
            # is the rebuild guard. Without this in the signature, plugging in a
            # second screen while the menu is open would leave it describing rows
            # the model does not have.
            len(self._topology().monitors),
        )

    def _rebuild(self, selected_action: str | None = None) -> None:
        settings = self.game.settings
        topology = self._topology()
        resolution = self._topology().resolve(settings.monitor)
        items = (
            MenuItem("display", "Display", self._display_label()),
            # Only where there is a choice to make. On a single-screen machine
            # there is nothing to pick and a row that always reads "Screen 1"
            # would be a row that cannot be acted on -- which is the dead-row
            # failure this screen has already produced once.
            *(
                (
                    MenuItem(
                        "monitor",
                        "Screen",
                        self._monitor_label(topology, resolution),
                        enabled=len(topology.monitors) > 1,
                    ),
                )
                if len(topology.monitors) > 1
                else ()
            ),
            MenuItem(
                "fullscreen_mode",
                "Fullscreen mode",
                self._fullscreen_mode_label(),
                enabled=settings.display is DisplayMode.FULLSCREEN,
            ),
            MenuItem("fit", "Scaling", self._fit_label()),
            MenuItem(
                "pixel_perfect",
                "Whole-pixel art",
                self._pixel_perfect_label(),
                fits_whole_pixel(self._window_size(), DEFAULT_FRAMING),
            ),
            MenuItem("vsync", "VSync", self._vsync_label()),
            MenuItem("frame_limit", "Frame limit", self._frame_limit_label()),
            MenuItem("scale", "UI scale", f"{settings.ui_scale:.1f}x"),
            # Debug only, because it is the one row here the game cannot honour
            # for a player who never sees the overlay: without ``DEBUG`` there
            # are no panels to size. Gated on ``Debug.is_enabled()`` rather than
            # a stored flag, since ``--debug`` is nothing but the environment
            # variable and this screen is built after the game is up.
            *(
                (
                    MenuItem(
                        "panel_scale",
                        "Debug panel scale",
                        f"{settings.panel_scale:g}x",
                    ),
                )
                if Debug.is_enabled()
                else ()
            ),
            MenuItem("reset", "Reset video settings"),
            MenuItem("back", "Back"),
            MenuItem("info", "Window", self._window_label(), enabled=False),
        )
        selected = next(
            (index for index, item in enumerate(items) if item.action == selected_action), 0
        )
        self.model.set_items(items, selected)

    def _topology(self) -> Topology:
        """The machine's displays, as the runtime last read them.

        From the game rather than from the detection module directly, because the
        runtime owns the cache: it is what notices a screen being plugged in, and
        a menu reading behind that would keep offering a display that is no longer
        attached. A screen that arrives is picked up by the poll, which this
        shares.
        """
        return self.game.topology()

    def _monitor_label(self, topology: Topology, resolution: Resolution) -> str:
        """The screen in use, and *why* it is that one when it is not the choice.

        The reason is the point of the row. A player who picked ``DP-1`` and
        unplugs it comes back to a menu reading "Screen 2" with no way to tell
        whether the game honoured them, ignored them, or guessed. Showing the
        reason turns a silent substitution into something the player can see and
        act on -- and it is why the stored name is never rewritten, so
        reconnecting that screen uses it again with no further action.
        """
        label = topology.label_for(resolution.monitor)
        if resolution.reason is ResolutionReason.NONE_CHOSEN:
            return f"{label} (auto)"
        if resolution.honoured:
            return label
        return f"{label} ({resolution.reason})"

    def _fit_label(self) -> str:
        return self.game.settings.fit.value

    def _fullscreen_mode_label(self) -> str:
        """The exclusive-fullscreen resolution, from what the driver reports.

        Read from ``list_modes`` rather than from a list this project wrote down,
        which is what makes it a choice the game can honour: every entry came out
        of the driver on this machine, on this panel. An entry that is no longer
        supported after a cable is swapped cannot be honoured, and the row says
        so rather than offering it.
        """
        modes = self.fullscreen_modes()
        if not modes:
            return "unavailable"
        stored = self.game.settings.fullscreen_mode
        if stored is None:
            return "display's own"
        found = f"{stored[0]}x{stored[1]}"
        return found if stored in modes else f"{found} (unavailable)"

    @staticmethod
    def fullscreen_modes() -> tuple[tuple[int, int], ...]:
        """Every mode the driver says this display supports, largest first.

        The driver's own answer rather than a catalogue. A hardcoded list is a
        claim about the player's panel that the game cannot check -- offering
        2560x1440 to a 1366x768 laptop is what that costs -- and this is the list
        that was removed for exactly that reason, now rebuilt from a source that
        can actually be asked.
        """
        try:
            return tuple(sorted(set(pygame.display.list_modes()), reverse=True))
        except pygame.error:
            return ()

    def _cycle_fullscreen_mode(self, action: InputAction) -> None:
        modes = self.fullscreen_modes()
        if not modes:
            return
        current = self.game.settings.fullscreen_mode
        index = modes.index(current) if current in modes else -1
        step = -1 if action is InputAction.UI_LEFT else 1
        # The first step lands on a real mode rather than on "auto": there is
        # nothing to the left of the display's own mode, and a cycle that sticks
        # at the end is a row that looks broken.
        if index < 0:
            chosen = modes[0] if step > 0 else modes[-1]
        else:
            chosen = modes[(index + step) % len(modes)]
        self._apply(self.game.settings.with_video(fullscreen_mode=chosen))

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
        """The whole-pixel row, which has to be able to say "not here" twice.

        Two different windows where the setting is honoured and the picture does
        not move: one too small to hold a whole multiple at all, and one already
        sized to one. The first is a refusal and says so; the second is the row
        working perfectly and has nothing to do, which without saying so reads as
        a dead row -- the label flips while the screen sits still, which is what
        a dead row looks like.

        The order is load-bearing rather than incidental: the two branches ask
        the same question in opposite directions and the refusal is the one that
        has to win, or a window too small for the art would be told there is
        nothing left to do.
        """
        size = self._window_size()
        if not fits_whole_pixel(size, DEFAULT_FRAMING):
            return "off (window too small)"
        if self.game.settings.pixel_perfect and already_a_whole_multiple(size, DEFAULT_FRAMING):
            return "on (already whole)"
        return self._on_off(self.game.settings.pixel_perfect)

    def _vsync_label(self) -> str:
        rate = self._screen_refresh_rate()
        suffix = f" {rate} Hz screen" if rate else ""
        if self.game.settings.vsync and not self._vsync_is_active():
            # The driver did not honour the request, and saying so is the whole
            # point of checking: the setting looks alive either way, and the only
            # symptom otherwise is a frame rate that never settles.
            #
            # What it must not do is answer "off". The player asked for on, the
            # player pressed something that visibly did land, and a row that
            # reads "off" after an "on" press is a row that reads as broken --
            # which is the same symptom the sentence was supposed to prevent, and
            # the exact reason these two rows were reported as dead. So the
            # setting is reported first and the driver's refusal is the caveat
            # on it, not the headline in place of it.
            return f"on (not honoured){suffix}"
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
        "monitor",
        "fullscreen_mode",
        "fit",
        "pixel_perfect",
        "vsync",
        "frame_limit",
        "scale",
        "panel_scale",
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
            "monitor": lambda: self._cycle_monitor(action),
            "fullscreen_mode": lambda: self._cycle_fullscreen_mode(action),
            "fit": lambda: self._cycle_fit(action),
            "pixel_perfect": lambda: self._cycle_bool(action, "pixel_perfect", click=click),
            "vsync": lambda: self._cycle_bool(action, "vsync", click=click),
            "frame_limit": lambda: self._cycle_frame_limit(action),
            "scale": lambda: self._cycle_scale(action),
            "panel_scale": lambda: self._cycle_panel_scale(action),
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
        #
        # **Confirm is a click.** It is the same discrete gesture with no
        # direction, which makes it the case above and not the one below, and it
        # used to be handled as ← anyway: it fell through to the same
        # `action is UI_RIGHT` test, so every confirm set the row *off* and none
        # could ever be turned on. Whole-pixel art and VSync were the two rows
        # it hit, and with a gamepad -- where confirm is how you press a button,
        # not how you step a value -- both were dead in the only direction a
        # player would try. Arrow keys worked, so the rows looked alive to a
        # test written with arrow keys and dead to a player holding one.
        current = getattr(self.game.settings, name)
        if click or action is InputAction.UI_CONFIRM:
            value = not current
        else:
            value = action is InputAction.UI_RIGHT
        self._apply(self.game.settings.with_video(**{name: value}))

    def _cycle_monitor(self, action: InputAction) -> None:
        """Step to the next display, and store it by name.

        By name and not by index, which is the only reason this row can be
        stored at all: the platform's enumeration order is not stable across
        boots, so an index in a settings file names a machine nobody can check.
        A name is resolved against the topology on the next launch, and if that
        screen is gone the row says so instead of the window quietly appearing
        somewhere else.

        The ladder ends on the primary rather than wrapping, and the primary is
        reachable again from anywhere: cycling is a walk through the displays
        this machine has, and a choice the player did not make is a legitimate
        thing to return to.
        """
        topology = self._topology()
        monitors = topology.monitors
        if len(monitors) < 2:
            return
        current = topology.resolve(self.game.settings.monitor).monitor
        step = -1 if action is InputAction.UI_LEFT else 1
        index = monitors.index(current) if current in monitors else 0
        chosen = monitors[(index + step) % len(monitors)]
        self._apply(self.game.settings.with_video(monitor=topology.label_for(chosen)))

    def _cycle_fit(self, action: InputAction) -> None:
        values = FIT_POLICIES
        current = self.game.settings.fit
        index = values.index(current) if current in values else 0
        step = -1 if action is InputAction.UI_LEFT else 1
        chosen = values[(index + step) % len(values)]
        # ``pixel_perfect`` is the older name for the integer policy and a v3 file
        # may still carry it, so choosing bars has to clear it -- otherwise the
        # saved flag would override the choice on the next launch.
        self._apply(
            self.game.settings.with_video(fit=chosen, pixel_perfect=chosen is FitPolicy.INTEGER)
        )

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

    def _cycle_panel_scale(self, action: InputAction) -> None:
        """Step the debug-panel scale, on its own ladder.

        ``PANEL_SCALE_VALUES`` and not ``SCALE_VALUES``: the panels start from
        ``Debug.FONT_SIZE = 24`` over a design frame, so the interface ladder's
        lowest step (0.8) is not a reduction at all -- at 1.0 only one of the
        five placeable panels finds a slot on a 640x480 window. This ladder goes
        to 0.4 for that, and 0.5 is where the full stack fits.
        """
        current = self.game.settings.panel_scale
        values = self.PANEL_SCALE_VALUES
        index = values.index(current) if current in values else 4
        step = -1 if action is InputAction.UI_LEFT else 1
        self._apply(self.game.settings.with_video(panel_scale=values[(index + step) % len(values)]))

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
                panel_scale=defaults.panel_scale,
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
