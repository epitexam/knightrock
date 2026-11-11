"""Video settings: the window's size, and how the picture is presented.

The only owner of the display settings; Options is navigation only. The rows
are the ``ROWS`` table. A setting with many values opens a list
(:class:`~src.application.scenes.option_screen.OptionScreen`) built in
:mod:`src.application.scenes.video_options`; a two-state setting toggles with
←/→. The sizes offered come from the panel the window is on, never from a
fixed catalogue.
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
from src.ui.text import t

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.application.game import Game

#: What a submenu builder returns: a title, the options, the value in force,
#: and what to call with the one picked.
Submenu = tuple[str, tuple[Option, ...], Any, Callable[[Any], None]]


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
    #: A section heading: shown, never focused.
    header: bool = False
    #: Only shown with ``DEBUG`` on.
    debug_only: bool = False
    #: The line shown under the list while the row is focused.
    note: Callable[[VideoScene], str] | None = None

    def __post_init__(self) -> None:
        jobs = sum(
            (
                self.submenu is not None,
                self.toggle is not None,
                self.run is not None,
                self.readout,
                self.header,
            )
        )
        if jobs > 1 or (jobs == 0 and self.action != "back"):
            raise ValueError(f"The {self.action!r} row must do exactly one thing")


def _kind(row: Row) -> str:
    """What the view says a press on ``row`` does."""
    if row.header:
        return "header"
    if row.submenu is not None:
        return "list"
    if row.toggle is not None:
        return "toggle"
    return ""


class VideoScene(MenuPage):
    scrollable = True
    TITLE = t("title.video")
    VALUE_FLASH_SECONDS = 0.5
    FOOTER = "footer.values"
    #: The help line of the lists this screen opens.
    SUBMENU_FOOTER = "footer.page"

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
            settings.fullscreen,
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
                t(row.label),
                row.value(self) if row.value is not None else "",
                enabled=not (row.readout or row.header),
                kind=_kind(row),
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

    def description(self) -> str:
        """The focused row's note, in the player's words."""
        current = self.model.current_item
        row = self._row(current.action) if current is not None else None
        return row.note(self) if row is not None and row.note is not None else ""

    def _on_off(self, value: bool) -> str:
        return t("value.on") if value else t("value.off")

    def _fullscreen_label(self) -> str:
        return self._on_off(self.game.settings.fullscreen)

    def _ui_scale_label(self) -> str:
        return f"{self.game.settings.ui_scale:.1f}x"

    def _ui_scale_note(self) -> str:
        density = 1.0 if self.game.presentation is None else self.game.presentation.density
        return t("note.ui_scale", effective=self.game.settings.ui_scale * density)

    def _panel_scale_label(self) -> str:
        return f"{self.game.settings.panel_scale:g}x"

    def _fit_label(self) -> str:
        """The policy the game draws with, which is not always the stored one."""
        return t(f"fit.{self.game.effective_fit().value}")

    def _fit_note(self) -> str:
        return t(f"fit.note.{self.game.effective_fit().value}")

    def _size_label(self) -> str:
        """The size the window has right now, not the one remembered for next launch."""
        width, height = self._window_size()
        return t("value.size", width=width, height=height)

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
        """The debug read-out: target size, density, and whether there are bars.

        Computed with the fit in force (:meth:`Game.effective_fit`), not the saved
        one, the same way the presentation computes it.
        """
        fitted = picture(self._window_size(), DEFAULT_FRAMING, self.game.effective_fit())
        density = density_for(fitted.target.size, DEFAULT_FRAMING)
        bars = "" if fitted.covered else " + bars"
        return f"{fitted.target.width}x{fitted.target.height} at {density:.2f}x{bars}"

    def _vsync_label(self) -> str:
        """On or off. Whether the driver honoured it is in the note: a request."""
        return self._on_off(self.game.settings.vsync)

    def _vsync_note(self) -> str:
        """What VSync does here, at which screen's rate.

        The driver cannot be asked whether it honoured the flag, so the note says
        "requested". The rate is left out when the window's screen is unknown.
        """
        if not self.game.settings.vsync:
            return t("note.vsync.off")
        rate = self._screen_refresh_rate()
        return t("note.vsync.on", rate=rate) if rate else t("note.vsync.on.unknown")

    def _frame_limit_label(self) -> str:
        limit = self.game.settings.frame_limit
        return t("value.uncapped") if limit is None else str(limit)

    def _frame_limit_note(self) -> str:
        """The limit is inert under VSync: the present paces, and the row says so."""
        return t("note.frame_limit.vsync" if self.game.settings.vsync else "note.frame_limit")

    def _screen_refresh_rate(self) -> int:
        """The refresh rate of the screen the window is on, or 0 when unknown.

        Not the primary's: on a two-screen desk that is the wrong number.
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
            t("title.fit"),
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
        """The list behind the window-size row, for the panel the window is on."""
        monitor = self.game.monitor()
        return (
            t("title.window_size"),
            video_options.window_size_options(
                monitor, self.game.settings.window_size, self._window_size()
            ),
            self.game.settings.window_size,
            self._apply_window_size,
        )

    def _apply_window_size(self, size: tuple[int, int] | None) -> None:
        """Ask for a window size, or ``None`` to forget it and keep the dragged size."""
        self._apply(self.game.settings.with_video(window_size=size))

    def _submenu_frame_limit(self) -> Submenu:
        return (
            t("title.frame_limit"),
            video_options.frame_limit_options(self.game.settings.vsync),
            self.game.settings.frame_limit,
            lambda value: self._apply(self.game.settings.with_video(frame_limit=value)),
        )

    def _submenu_scale(self) -> Submenu:
        density = 1.0 if self.game.presentation is None else self.game.presentation.density
        return (
            t("title.ui_scale"),
            video_options.ui_scale_options(self.game.settings.ui_scale, density),
            self.game.settings.ui_scale,
            lambda value: self._apply(self.game.settings.with_video(ui_scale=value)),
        )

    def _submenu_panel_scale(self) -> Submenu:
        return (
            t("title.panel_scale"),
            video_options.panel_scale_options(),
            self.game.settings.panel_scale,
            lambda value: self._apply(self.game.settings.with_video(panel_scale=value)),
        )

    def _handle_row_value_navigation(self, routed: RoutedInput) -> bool:
        """←/→ and Enter act on the focused value row.

        On a disabled row they are swallowed: passed on, the model would act on the
        nearest enabled row instead.
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
        # ← sets off and → sets on, so the two keys differ. A click or Enter has
        # no direction and flips: treated as ←, Enter could never turn a row on.
        current = getattr(self.game.settings, name)
        if click or action is InputAction.UI_CONFIRM:
            value = not current
        else:
            value = action is InputAction.UI_RIGHT
        self._apply(self.game.settings.with_video(**{name: value}))

    def _reset(self) -> None:
        """Put the video settings back to their defaults, and only those.

        The bindings are kept, and so is the window size: it is where the player
        dragged the window, not a picture choice. ``fit`` and ``pixel_perfect``
        reset together, as they are one setting.
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
        Row("section:window", "section.window", header=True),
        Row(
            "size",
            "video.size",
            _size_label,
            submenu=_submenu_size,
            note=lambda scene: t("note.size"),
        ),
        Row(
            "fullscreen",
            "video.fullscreen",
            _fullscreen_label,
            toggle="fullscreen",
            note=lambda scene: t("note.fullscreen"),
        ),
        Row("section:picture", "section.picture", header=True),
        Row("fit", "video.fit", _fit_label, submenu=_submenu_fit, note=_fit_note),
        Row("section:performance", "section.performance", header=True),
        Row("vsync", "video.vsync", _vsync_label, toggle="vsync", note=_vsync_note),
        Row(
            "frame_limit",
            "video.frame_limit",
            _frame_limit_label,
            submenu=_submenu_frame_limit,
            note=_frame_limit_note,
        ),
        Row("section:interface", "section.interface", header=True),
        Row(
            "scale", "video.ui_scale", _ui_scale_label, submenu=_submenu_scale, note=_ui_scale_note
        ),
        Row(
            "panel_scale",
            "video.panel_scale",
            _panel_scale_label,
            submenu=_submenu_panel_scale,
            # No overlay without DEBUG, so nothing to size.
            debug_only=True,
        ),
        Row("reset", "video.reset", run=_reset, note=lambda scene: t("note.reset")),
        Row("back", "row.back"),
        # A diagnostic, in the debug overlay's terms: the target, its density, bars.
        Row(
            "info",
            "video.readout",
            _window_label,
            readout=True,
            debug_only=True,
        ),
    )
    #: The rows that open a list, and the rows that toggle, read off the table.
    SUBMENUS = tuple(row.action for row in ROWS if row.submenu is not None)
    CYCLING_ROWS = tuple(row.action for row in ROWS if row.toggle is not None)
