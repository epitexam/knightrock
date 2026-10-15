"""Video settings: how to occupy the screen, and how it is presented.

Sole owner of the display settings. They used to be duplicated in the Options
hub, which let the player change the same value from two places; the Options
screen is now navigation only.

This screen is a hub. Every setting with more than a handful of values opens a
list (:class:`~src.application.scenes.option_screen.OptionScreen`), because
cycling is only a reasonable control for two to four values and some of these
are not: the driver reports 28 fullscreen modes on this panel, so a cycle took up
to 27 presses and offered no way to discover the value existed. The lists
themselves live in :mod:`src.application.scenes.video_options`, so what a setting
*offers* is decided without a screen in the way.

Left as direct ←/→ cycling, on purpose, are the rows that really are two or three
states: the display mode, VSync, and the whole-pixel question -- which is no
longer its own row, because it is the same setting as the integer fit policy and
sitting next to it as a separate toggle produced a row that changed its label and
changed nothing on screen. It is an entry inside the fit list now, where the
sentence explaining what whole-pixel art is has room to be read.

Still no resolution *catalogue*. A hardcoded list of window sizes is a claim
about the player's monitor the game cannot check -- offering 2560x1440 to a
1366x768 laptop is what that costs. The fullscreen list is the opposite: it is
read from the driver on this machine and then filtered to modes the chosen panel
can actually display, which is what makes it a claim the game can stand behind.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pygame

from src.application.scene import Scene
from src.application.scenes import video_options
from src.application.scenes.option_screen import Option, OptionScreen
from src.application.settings_store import UserSettings
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import FitPolicy, density_for, picture
from src.core.display.mode import DisplayMode
from src.core.display.monitors import Resolution, ResolutionReason, Topology
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.core.settings import Debug
from src.ui.menu_model import MenuAction, MenuItem, MenuModel
from src.ui.menu_view import MenuView

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.core.game import Game

#: What a submenu builder hands back: a title, the options, which one is in
#: force, and what to do when one is picked. A tuple rather than four
#: arguments because these are read positionally at the call site and a named
#: structure here would need a class for one use.
#:
#: Generic in the value type, because each builder knows exactly what its options
#: carry -- a monitor name, a ``FitPolicy``, an ``int | None`` -- and an alias
#: that erased that would force every caller to cast what it just built.
Submenu = tuple[str, tuple[Option, ...], Any, Callable[[Any], None]]

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
    VALUE_FLASH_SECONDS = 0.5
    FOOTER = "↑↓ row · ←→ change · Esc back"
    #: Where a list row goes when it is opened, and what it says on the way out.
    #: The picker draws its own footer, so it does not inherit this one.
    SUBMENU_FOOTER = "↑↓ row · Enter select · Esc back"

    #: Which list each row owns. Named rather than bound to the builders here,
    #: because the builders are methods defined further down and a class body
    #: cannot reference them -- and a table of names is what the row lists can be
    #: checked against, which is the check that catches a row with no list.
    SUBMENUS = (
        "monitor",
        "resolution",
        "fit",
        "frame_limit",
        "scale",
        "panel_scale",
    )
    #: Kept as the older name for the callers that read it, and as the one place
    #: a row's fate is decided: every row on this screen is in this tuple, in
    #: ``CYCLING_ROWS``, or in ``handle_routed``'s named branches, and a row in
    #: none of the three is the dead row this screen has produced twice.
    SUBMENU_ROWS = SUBMENUS

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
            MenuItem("display", "Display mode", self._display_label()),
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
                    ),
                )
                if len(topology.monitors) > 1
                else ()
            ),
            # One row, three modes, and it is always live. It was a disabled
            # "Fullscreen mode" outside fullscreen, which is worse than it
            # sounds: the focus walk skips a disabled row and a click on one
            # does nothing, so the row was drawn, aimable, and inert -- the
            # dead-row failure this screen has produced twice.
            #
            # It was then hidden in borderless, on the grounds that there is
            # nothing to choose. That was wrong twice over. A borderless window is
            # a real window and SDL will give it a size other than the panel's --
            # measured: FULLSCREEN|NOFRAME at 1600x900 yields a 1600x900
            # borderless window, positioned and draggable. And `auto` resolves to
            # borderless on any 16:9 desktop, so hiding the row took it away from
            # most players by default, on the first launch, with no setting of
            # theirs involved.
            #
            # So the row asks the question that is real in every mode: what size
            # should the window be. In exclusive fullscreen it means the mode the
            # driver is asked for; otherwise it means the window's own size, and
            # borderless is a window like any other.
            MenuItem(
                "resolution",
                self._resolution_label(settings.display),
                self._resolution_value(settings.display),
            ),
            MenuItem("fit", "Picture fit", self._fit_label()),
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

    def _resolution_label(self, mode: DisplayMode) -> str:
        """What the row is called, which depends on the mode it applies to.

        Naming it for the mode rather than for the setting is the point: a row
        called "Fullscreen mode" that is greyed out in windowed mode is a row
        asking the player to work out why, and one called "Window size" in
        fullscreen is asking the same question the other way.
        """
        return "Fullscreen mode" if mode is DisplayMode.FULLSCREEN else "Window size"

    def _resolution_value(self, mode: DisplayMode) -> str:
        """The row's value: the fullscreen mode, or the size the window has.

        In windowed mode this reads the size the window *actually has*, not the
        one remembered for next launch -- those differ after the player drags it,
        and a row reporting the remembered value while the window is another size
        is the lie this menu used to tell about a resolution.
        """
        if mode is not DisplayMode.FULLSCREEN:
            granted = self._window_size()
            return f"{granted[0]} x {granted[1]}"
        stored = self.game.settings.fullscreen_mode
        if stored is None:
            return "the display's own mode"
        found = f"{stored[0]}x{stored[1]}"
        monitor = self._topology().resolve(self.game.settings.monitor).monitor
        if stored[0] > monitor.size[0] or stored[1] > monitor.size[1]:
            return f"{found} (unavailable)"
        return found

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
        the game was not using. Three facts, all derived and none stored: how big
        the picture is, how many pixels a world unit gets there, and whether
        anything around it is a bar.

        Derived through :func:`picture` **with the policy in force**, which is the
        whole of this fix: it used to call ``letterbox(..., pixel_perfect=)`` and
        so described the picture under *bars* whatever the player had selected.
        Under zoom -- which fills the window and crops the edges -- a window of
        any other shape than the framing's was therefore reported with bars it did
        not have, at a size it was not drawn at. A read-out that does not read out
        is the same defect as the row that showed a number the game was not using,
        which is what this line replaced.

        The presentation is not asked, and that is deliberate rather than a
        shortcut: it computes this from the window size and the same policy, so
        the two agree by construction, and a pure function of two settings can be
        read without a window existing.
        """
        fitted = picture(self._window_size(), DEFAULT_FRAMING, self.game.settings.fit)
        density = density_for(fitted.target.size, DEFAULT_FRAMING)
        bars = "" if fitted.covered else " + bars"
        return f"{fitted.target.width}x{fitted.target.height} at {density:.2f}x{bars}"

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

    def _screen_refresh_rate(self) -> int:
        """The refresh rate of the screen the window is *on*, or 0 when nobody can say.

        It used to be the **primary** display's rate, which is a claim about a
        screen the window may not be on: on a two-panel desk the player reading
        180Hz on the VSync row while the window sat on the 60Hz panel was reading
        the wrong number, and one they had no way to tell apart from the right one.

        So it reads the rate off the monitor that holds the window, and says
        nothing at all when that monitor cannot be established -- a row with no
        screen in it is a missing hint, where a wrong rate is a fact.
        """
        monitor = self.game.window_monitor()
        return monitor.refresh_rate if monitor is not None else 0

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
        if action in self.SUBMENU_ROWS:
            # A click on a list row opens the list, the same as → and as Enter.
            # It used to step the value instead, which is a control that only
            # makes sense for two or three states -- and on a 28-entry list it
            # was a click that moved a value one step somewhere the player was
            # not looking.
            self._open(action)
        elif action in self.CYCLING_ROWS:
            self._cycle(action, InputAction.UI_RIGHT, click=True)
        elif action == "reset":
            self._reset()
        elif action == "back":
            self.game.scene_manager.pop()
            return MenuAction.BACK
        return action

    #: Rows whose value a press -- or a click -- steps, because there are only
    #: two or three of them and a list would be a worse control.
    CYCLING_ROWS = ("display", "vsync")

    def _open(self, action: str) -> None:
        """Push the list a row owns.

        The builder is looked up by name because the builders are methods and a
        class-body table cannot reference one. A row with no builder is the
        dead-row bug, so it is logged rather than swallowed: a row that refuses
        every press is indistinguishable from a broken key, and the log is the
        only thing that says which one.
        """
        builder = getattr(self, f"_submenu_{action}", None)
        if builder is None:
            logger.warning("The %r row has no list to open", action)
            return
        title, options, selected, apply = builder()
        self.game.scene_manager.push(
            OptionScreen(
                self.game,
                title,
                options,
                apply,
                selected=selected,
                footer=self.SUBMENU_FOOTER,
                on_back=self._rebuild,
            )
        )

    def _submenu_monitor(self) -> Submenu:
        topology = self._topology()
        resolution = topology.resolve(self.game.settings.monitor)
        return (
            "SCREEN",
            video_options.screen_options(topology, resolution),
            resolution.monitor.name or None,
            lambda name: self._apply(self.game.settings.with_video(monitor=name)),
        )

    def _submenu_fit(self) -> Submenu:
        return (
            "PICTURE FIT",
            video_options.fit_options(self._window_size(), self.game.settings.fit),
            self.game.settings.fit,
            self._apply_fit,
        )

    def _apply_fit(self, policy: FitPolicy) -> None:
        """Choose a fit policy, keeping the whole-pixel flag consistent with it.

        ``pixel_perfect`` is the older name for the integer policy and a v3 file
        may still carry it, so it is written alongside rather than left to
        override the choice on the next launch -- which is what used to happen.
        """
        self._apply(
            self.game.settings.with_video(fit=policy, pixel_perfect=policy is FitPolicy.INTEGER)
        )

    def _submenu_resolution(self) -> Submenu:
        """The list behind the one resolution row, whichever mode is in force.

        Two settings behind one row, because only one of them is ever the live
        one: the mode the driver is asked for while the game has taken the panel
        over, and the window's own size in every other mode -- including
        borderless, where the window is still a window with a size.

        That inclusion is the point of this row existing at all. Hiding it in
        borderless removed it from the default on any 16:9 screen, because
        ``auto`` resolves to borderless there, and a player who never touched the
        display mode would have had one fewer setting than a player who did.
        """
        topology = self._topology()
        monitor = topology.resolve(self.game.settings.monitor).monitor
        if self.game.settings.display is DisplayMode.FULLSCREEN:
            return (
                "FULLSCREEN MODE",
                video_options.fullscreen_mode_options(
                    self.fullscreen_modes(),
                    monitor,
                    self.game.settings.fullscreen_mode,
                ),
                self.game.settings.fullscreen_mode,
                lambda mode: self._apply(self.game.settings.with_video(fullscreen_mode=mode)),
            )
        return (
            "WINDOW SIZE",
            video_options.window_size_options(
                monitor, self.game.settings.window_size, self._window_size()
            ),
            self.game.settings.window_size,
            self._apply_window_size,
        )

    def _apply_window_size(self, size: tuple[int, int] | None) -> None:
        """Ask for a window size, or forget the preference and follow the drag.

        ``None`` clears the remembered size rather than storing one, which is
        what makes the window follow whatever the player drags it to next time --
        the honest answer for a setting whose whole point is that the window
        manager owns it.
        """
        self._apply(self.game.settings.with_video(window_size=size))

    def _submenu_frame_limit(self) -> Submenu:
        return (
            "FRAME LIMIT",
            video_options.frame_limit_options(),
            self.game.settings.frame_limit,
            lambda value: self._apply(self.game.settings.with_video(frame_limit=value)),
        )

    def _submenu_scale(self) -> Submenu:
        density = 1.0 if self.game.presentation is None else self.game.presentation.density
        return (
            "UI SCALE",
            video_options.ui_scale_options(self.game.settings.ui_scale, density),
            self.game.settings.ui_scale,
            lambda value: self._apply(self.game.settings.with_video(ui_scale=value)),
        )

    def _submenu_panel_scale(self) -> Submenu:
        return (
            "DEBUG PANEL SCALE",
            video_options.panel_scale_options(),
            self.game.settings.panel_scale,
            lambda value: self._apply(self.game.settings.with_video(panel_scale=value)),
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
        if current.action in self.SUBMENU_ROWS:
            self._open(current.action)
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
            "vsync": lambda: self._cycle_bool(action, "vsync", click=click),
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
