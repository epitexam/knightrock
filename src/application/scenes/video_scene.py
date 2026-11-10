"""Video settings: the window's size, and how the picture is presented.

Sole owner of the display settings. They used to be duplicated in the Options
hub, which let the player change the same value from two places; the Options
screen is now navigation only.

This screen is a hub. Every setting with more than a handful of values opens a
list (:class:`~src.application.scenes.option_screen.OptionScreen`), because
cycling is only a reasonable control for two to four values. The lists themselves
live in :mod:`src.application.scenes.video_options`, so what a setting *offers*
is decided without a screen in the way.

Left as direct ←/→ cycling, on purpose, is the one row that really is two states:
VSync. The display mode and the chosen screen lived here too, and both are gone.
The game is a window, so there is one set of flags; the player chooses its size
and the window manager owns where it sits.

Still no resolution *catalogue*. A hardcoded list of window sizes is a claim
about the player's monitor the game cannot check -- offering 2560x1440 to a
1366x768 laptop is what that costs. The sizes offered are derived from the panel
in force and filtered to what it can hold, which is what keeps them checkable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pygame

from src.application.scenes import video_options
from src.application.scenes.menu_page import MenuPage
from src.application.scenes.option_screen import Option, OptionScreen
from src.application.settings_store import UserSettings
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.letterbox import FitPolicy, density_for, picture
from src.core.input.event_router import RoutedInput
from src.core.input.input_actions import InputAction
from src.core.settings import Debug
from src.ui.menu_model import MenuAction, MenuItem

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.core.game import Game

#: What a submenu builder hands back: a title, the options, which one is in
#: force, and what to do when one is picked. A tuple rather than four
#: arguments because these are read positionally at the call site and a named
#: structure here would need a class for one use.
#:
#: Generic in the value type, because each builder knows exactly what its options
#: carry -- a ``FitPolicy``, an ``int | None`` -- and an alias that erased that
#: would force every caller to cast what it just built.
Submenu = tuple[str, tuple[Option, ...], Any, Callable[[Any], None]]

#: The fit policies, in the order the row steps through them. Bars first because
#: it is the only one that is never surprising, and zoom last because it is the
#: one that costs the player some of the picture.
FIT_POLICIES = (FitPolicy.BARS, FitPolicy.INTEGER, FitPolicy.ZOOM)


@dataclass(frozen=True)
class Row:
    """One row of the Video screen: what it reads, and what pressing it does.

    A row does exactly one thing -- opens a list, toggles a setting, runs an
    action, or only reports -- and the one row allowed to do none of them is
    Back. A row with nothing to do is refused when the table is built, which is
    what makes the "dead row" this screen produced twice impossible.
    """

    action: str
    label: str
    value: Callable[[VideoScene], str] | None = None
    #: Builds the list the row opens.
    submenu: Callable[[VideoScene], Submenu] | None = None
    #: The boolean setting the row toggles.
    toggle: str | None = None
    #: What the row does when pressed.
    run: Callable[[VideoScene], None] | None = None
    #: A read-out: shown, never focused.
    readout: bool = False
    #: Only shown with ``DEBUG`` on.
    debug_only: bool = False

    def __post_init__(self) -> None:
        jobs = sum(
            (self.submenu is not None, self.toggle is not None, self.run is not None, self.readout)
        )
        if jobs > 1 or (jobs == 0 and self.action != "back"):
            raise ValueError(f"The {self.action!r} row must do exactly one thing")


class VideoScene(MenuPage):
    scrollable = True
    TITLE = "VIDEO"
    VALUE_FLASH_SECONDS = 0.5
    FOOTER = "↑↓ row · ←→ change · Esc back"
    #: Where a list row goes when it is opened, and what it says on the way out.
    #: The picker draws its own footer, so it does not inherit this one.
    SUBMENU_FOOTER = "↑↓ row · Enter select · Esc back"

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self._signature = self._current_signature()
        self._flash_row = -1
        self._flash_remaining = 0.0
        self._rebuild()

    # ------------------------------------------------------------------ rows

    def _current_signature(self) -> tuple[object, ...]:
        """The settings this screen renders, used to skip redundant rebuilds."""
        settings = self.game.settings
        return (
            settings.pixel_perfect,
            settings.vsync,
            settings.frame_limit,
            settings.ui_scale,
            settings.panel_scale,
            settings.fit,
            # The debug row is conditional on this, and the rebuild is skipped
            # when the signature is unchanged -- so without the flag in the
            # signature, flipping DEBUG mid-session would leave the menu
            # describing a set of rows the model does not have.
            Debug.is_enabled(),
            # The rate the window is actually on, so the VSync row follows the
            # window from one panel to another.
            self._screen_refresh_rate(),
            self._window_size(),
        )

    def _rebuild(self, selected_action: str | None = None) -> None:
        """The rows from :attr:`ROWS`, focus kept on ``selected_action``."""
        items = tuple(
            MenuItem(
                row.action,
                row.label,
                row.value(self) if row.value is not None else "",
                enabled=not row.readout,
            )
            for row in self.ROWS
            if not row.debug_only or Debug.is_enabled()
        )
        selected = next(
            (index for index, item in enumerate(items) if item.action == selected_action), 0
        )
        self.model.set_items(items, selected)

    def _row(self, action: str) -> Row | None:
        return next((row for row in self.ROWS if row.action == action), None)

    def _ui_scale_label(self) -> str:
        return f"{self.game.settings.ui_scale:.1f}x"

    def _panel_scale_label(self) -> str:
        return f"{self.game.settings.panel_scale:g}x"

    def _fit_label(self) -> str:
        """The policy the game draws with, which is not always the stored one."""
        return self.game.effective_fit().value

    def _size_label(self) -> str:
        """The size the window has right now.

        The size the window *actually has*, not the one remembered for next
        launch -- those differ after the player drags it, and a row reporting the
        remembered value while the window is another size is the lie this menu
        used to tell about a resolution.
        """
        granted = self._window_size()
        return f"{granted[0]} x {granted[1]}"

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

        Derived through :func:`picture` **with the policy in force** -- the one
        the game draws with (:meth:`Game.effective_fit`), not the one the settings
        file holds. The two differ for exactly one player, and it is the one this
        row exists for: a file migrated from v3 with whole-pixel art on and no
        ``fit`` key of its own has ``settings.fit`` answering "bars" while the
        game is drawing at whole pixels, so reading the setting here would report
        a target size nothing is drawn at.

        The presentation is not asked, and that is deliberate rather than a
        shortcut: it computes this from the window size and the same policy, so
        the two agree by construction, and a pure function of two settings can be
        read without a window existing.
        """
        fitted = picture(self._window_size(), DEFAULT_FRAMING, self.game.effective_fit())
        density = density_for(fitted.target.size, DEFAULT_FRAMING)
        bars = "" if fitted.covered else " + bars"
        return f"{fitted.target.width}x{fitted.target.height} at {density:.2f}x{bars}"

    def _vsync_label(self) -> str:
        """What the row reports about vertical synchronisation: a *request*.

        The game can pass the flag and can recreate the window for it, and it
        cannot find out whether the driver honoured it. pygame-ce's
        ``is_vsync()`` looks like that check and is not one: it returns the flag
        the game itself passed to ``set_mode`` -- measured, it answers ``True``
        under the dummy driver where no swap interval can exist, and ``True``
        under X11 without any context to query. Reading the driver's opinion
        would need ``SDL_GL_GetSwapInterval`` through ``ctypes`` against a
        context pygame does not expose as its own, which is the fragile
        half-answer the probe module exists to avoid.

        So the label qualifies the request instead of claiming an effect, and
        the honest headline is ``on · requested`` rather than ``on``: the player
        reads that the flag was sent, and that the rate they get is the panel's
        -- which is also the one shown here, for the panel the window is on.
        A row that read ``off`` after an ``on`` press was one of the two dead
        rows this screen produced; a row that claims an honoured vsync the
        driver dropped is a lie in the other direction.
        """
        rate = self._screen_refresh_rate()
        suffix = f" {rate} Hz screen" if rate else ""
        if self.game.settings.vsync:
            return f"on · requested{suffix}"
        return f"off{suffix}"

    def _frame_limit_label(self) -> str:
        """The frame limit, with the one condition it is subject to made visible.

        The limit is what the clock paces to, and the clock only paces when
        vsync is not already doing it: :meth:`Game._frame_delta` ticks against
        a ceiling no menu value can bite, precisely so a working present is the
        only pacer. With vsync on, then, every ladder value is ignored -- and a
        row reading ``60`` with ``on · requested`` above it is a row that reads
        as two working settings when one is inert. Saying it is cheap.
        """
        limit = self.game.settings.frame_limit
        label = "Uncapped" if limit is None else str(limit)
        if self.game.settings.vsync:
            label += " · ignored (VSync)"
        return label

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

    def handle_value_keys(self, routed: RoutedInput) -> str | None:
        return MenuAction.ACTIVATE if self._handle_row_value_navigation(routed) else None

    def act(self, action: str) -> None:
        row = self._row(action)
        if row is None:
            return
        if row.submenu is not None:
            # A click on a list row opens the list, the same as → and as Enter.
            self._open(action)
        elif row.toggle is not None:
            self._cycle_bool(InputAction.UI_RIGHT, row.toggle, click=True)
        elif row.run is not None:
            row.run(self)

    def _open(self, action: str) -> None:
        """Push the list a row owns."""
        row = self._row(action)
        if row is None or row.submenu is None:
            logger.warning("The %r row has no list to open", action)
            return
        title, options, selected, apply = row.submenu(self)
        self.game.scene_manager.push(
            OptionScreen(
                self.game,
                title,
                options,
                apply,
                selected=selected,
                footer=self.SUBMENU_FOOTER,
                # Back on the row that opened the list, not on the first row.
                on_back=lambda: self._rebuild(action),
            )
        )

    def _submenu_fit(self) -> Submenu:
        return (
            "PICTURE FIT",
            video_options.fit_options(self._window_size()),
            self.game.effective_fit(),
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

    def _submenu_size(self) -> Submenu:
        """The list behind the window-size row.

        The window is the only thing the display settings produce now, so this
        list is the only display choice on the screen: how big to open. The panel
        the sizes are measured against is the one :meth:`Game.monitor` anchors
        (Rule W) -- the panel the *window* is on, primary until there is a window
        -- because a list derived from a panel the window is not on would describe
        a screen the player is not looking at, which is exactly the mismatch the
        read-out bug made.
        """
        monitor = self.game.monitor()
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
            video_options.frame_limit_options(self.game.settings.vsync),
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

        A row that is *not* usable -- the read-out of the window -- swallows the
        press instead of passing it on. The alternative was worse than a dead
        key: the menu model answers an action on a disabled row by activating
        the nearest enabled one, so Enter on the read-out line silently changed
        the setting on the row next to it. A row that cannot be used has to do
        nothing, visibly.
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
        row = self._row(current.action)
        if row is None:
            return False
        if row.submenu is not None:
            self._open(current.action)
            return True
        if row.toggle is not None:
            self._cycle_bool(routed.action, row.toggle)
            return True
        return False

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

        ``fit`` and ``pixel_perfect`` go together, as they do in
        :meth:`_apply_fit`: those two names have described one setting since the
        whole-pixel row was folded into the fit picker, and resetting one and
        leaving the other would leave a file where the flag said bars and the
        policy said integer. Reset is when that pairing is easiest to forget,
        which is why the pairing is stated here and not only there.

        ``window_size`` is *not* reset, on purpose, and the difference is what
        the two kinds of preference are. Fit, vsync and the scales are choices
        about the picture; the window's size is where the player put the window,
        which they chose by dragging, not by selecting -- resetting it would
        undo their last gesture with a menu press. The row is named for what it
        resets, and this is why the list above it is the list it is.
        """
        defaults = UserSettings()
        self._apply(
            self.game.settings.with_video(
                pixel_perfect=defaults.pixel_perfect,
                fit=defaults.fit,
                vsync=defaults.vsync,
                frame_limit=defaults.frame_limit,
                ui_scale=defaults.ui_scale,
                panel_scale=defaults.panel_scale,
            )
        )

    def _apply(self, settings: UserSettings) -> None:
        selected_action = self.model.current_item.action if self.model.current_item else None
        try:
            self.game.apply_settings(settings)
        except pygame.error as error:
            # The platform refused the window. ``apply_settings`` rolled back, so
            # the game is still in the state it was in: say so rather than crash.
            logger.warning("The display refused the new settings: %s", error)
            self.game.notice("The display refused that setting.", "Nothing was changed.")
        self._rebuild(selected_action)
        self._signature = self._current_signature()
        self._flash_value_change()

    def highlighted(self) -> int:
        return self._flash_row

    def draw(self, surface: pygame.Surface) -> None:
        if self._current_signature() != self._signature:
            self._signature = self._current_signature()
            focused = self.model.current_item.action if self.model.current_item else None
            self._rebuild(focused)
        super().draw(surface)

    # ------------------------------------------------------------- the table

    #: Every row on this screen, in order. The single place a row is declared.
    ROWS: tuple[Row, ...] = (
        Row("size", "Window size", _size_label, submenu=_submenu_size),
        Row("fit", "Picture fit", _fit_label, submenu=_submenu_fit),
        Row("vsync", "VSync", _vsync_label, toggle="vsync"),
        Row("frame_limit", "Frame limit", _frame_limit_label, submenu=_submenu_frame_limit),
        Row("scale", "UI scale", _ui_scale_label, submenu=_submenu_scale),
        Row(
            "panel_scale",
            "Debug panel scale",
            _panel_scale_label,
            submenu=_submenu_panel_scale,
            # No overlay without DEBUG, so nothing to size.
            debug_only=True,
        ),
        Row("reset", "Reset video settings", run=_reset),
        Row("back", "Back"),
        Row("info", "Window", _window_label, readout=True),
    )
    #: The rows that open a list, and the rows that toggle, read off the table.
    SUBMENUS = tuple(row.action for row in ROWS if row.submenu is not None)
    CYCLING_ROWS = tuple(row.action for row in ROWS if row.toggle is not None)
