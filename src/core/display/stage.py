"""The window: mode, size, position, monitor and vsync.

Deliberately the only module in the game that calls ``set_mode``. Everything
else draws into a ``Viewport`` and never learns that a window exists.

Three display modes, three different things
------------------------------------------
They used to be two different things wearing three names, because ``BORDERLESS``
and ``FULLSCREEN`` both passed ``pygame.FULLSCREEN`` and nothing else. The
``mode`` enum's own docstring promised otherwise -- borderless "changes nothing
on the player's system: no mode change to fail, no refresh-rate change, nothing
to redo when a hybrid-GPU laptop switches the display over to its integrated
chip mid-session" -- and the flags never delivered it. Asking for
``SDL_WINDOW_FULLSCREEN`` *is* asking the driver for a mode change, which is
exactly what that sentence said borderless would not do, so the shipped default
was the risky one.

The distinction is made here, and it is a flag:

- **window**: ``RESIZABLE``, a real window, placed and sized by the player.
- **borderless**: ``FULLSCREEN | NOFRAME`` at the monitor's *usable* size. A
  window with no decoration covering the panel, at the resolution the panel is
  already running, so no mode is changed and there is nothing to restore.
- **fullscreen**: ``FULLSCREEN`` alone, at a mode the driver reported. This one
  does ask for a real mode change, and leaving it restores the previous one.

Measured on the development machine, both fullscreen flags at a requested
1280x720 produce a 1280x720 surface -- the driver does change mode. That is
correct for ``fullscreen`` and defeats the point of ``borderless``, which asks
for the *usable* size (1920x1048 there) instead and so never leaves the desktop
where it found it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pygame

from .mode import DisplayMode
from .monitors import (
    MIN_WINDOW,
    Monitor,
    centre_on,
    fit_position,
    fit_size,
    opening_size,
)

logger = logging.getLogger(__name__)

#: How far a window's own title bar has to stay inside the usable area for the
#: player to be able to grab it. Used by the position clamp.
TITLE_BAR_KEEP = (64, 32)

#: How many times the window is asked for the size it was given before the
#: refusal is believed. One is not enough: measured, the first ``set_mode`` that
#: changes the flags is dropped by SDL and the second is honoured, and the same
#: alternation is visible on a display change -- one of the two requests lands
#: per window recreation, so a request that checks "did it take?" and gives up is
#: a coin toss. Two asks and a check are cheap; a window at the wrong size is not.
SIZE_ATTEMPTS = 2

#: How many times a placement is re-issued before the window is believed to be
#: where the player asked for. Same measurement as :data:`SIZE_ATTEMPTS`, applied
#: to the position: the platform re-places a window after a refused size, so the
#: one request made right after ``set_mode`` can be the one that is lost.
PLACE_ATTEMPTS = 3

#: Milliseconds to give the window manager between two placement requests.
#: Measured on the development machine: a move is applied asynchronously, and
#: three moves issued in the same instant are read back from before all three --
#: the game sees its own previous position and concludes the platform refused.
PLACE_RETRY_WAIT_MS = 30


@dataclass(frozen=True)
class WindowSpec:
    """What the player asked for, before the platform has its say.

    A plain value rather than ``UserSettings``, so this module stays free of the
    application layer and can be driven straight from a test.

    ``monitor`` is an index into the *current* topology, resolved by the caller
    from the name the settings file holds. It is validated here against the
    topology before it reaches ``set_mode``, because pygame answers an
    out-of-range display index with ``displayIndex must be in the range 0 - 0``
    -- a crash on the very first frame, on the machine least able to cope with it.
    """

    mode: DisplayMode = DisplayMode.BORDERLESS
    monitor: int = 0
    vsync: bool = False
    #: Remembered window geometry, honoured in window mode only and clamped to
    #: the monitor it opens on. ``None`` means "let the machine decide", which is
    #: a first launch and a reset, not a default the file ever holds.
    size: tuple[int, int] | None = None
    position: tuple[int, int] | None = None
    #: The mode to ask for in exclusive fullscreen. ``None`` is ``(0, 0)``, which
    #: is how SDL is told to use the display's current mode. A value the driver
    #: does not report is refused here rather than at ``set_mode``, because
    #: pygame's answer to an unsupported mode is a crash and this is the one place
    #: that knows what the driver supports.
    fullscreen_mode: tuple[int, int] | None = None


class Stage:
    """The OS window the game is presented in.

    Three rules earn their keep here, and the third is the one that was missing:

    * **The surface is measured, never assumed.** The size actually granted is
      read back off the surface rather than trusted from the request, because with
      high-DPI windows the two differ and every layout downstream would be quietly
      wrong.
    * **Placement is computed from real display bounds.** Centring needs the
      monitor's origin on the virtual desktop, which
      :mod:`src.core.display.sdl_probe` supplies; a guess puts the window on the
      other monitor, which is worse than not placing it at all.
    * **A request that was not honoured is made again.** Measuring is only half
      of it. Both ``set_mode`` and the window placement can be accepted by SDL
      and then dropped by the window manager, and the game is the only thing in
      the chain that can tell. Measured here: the first ``set_mode`` after a flag
      change comes back at the desktop's size whatever was asked for, and the
      display index in it moves a window that already exists exactly never. One
      request and a shrug is how the video menu learned to change its label and
      nothing else.
    """

    def __init__(self, spec: WindowSpec, monitor: Monitor) -> None:
        self.spec = spec
        self.monitor = monitor
        self.surface = self._create(spec, monitor)

    @property
    def size(self) -> tuple[int, int]:
        """The window's granted size, read back from the surface."""
        return self.surface.get_size()

    def rebuild(self, spec: WindowSpec, monitor: Monitor) -> pygame.Surface:
        """Recreate the window for a new specification and return its surface."""
        self.spec = spec
        self.monitor = monitor
        self.surface = self._create(spec, monitor)
        return self.surface

    def _create(self, spec: WindowSpec, monitor: Monitor) -> pygame.Surface:
        """Open the window, and place it.

        Order matters: the size is asked for first, because a windowed placement
        depends on how big the window turned out to be, and ``set_mode`` is what
        tells us that. Placing afterwards means the clamp works against the real
        size rather than the requested one.

        **And the size is asked for more than once when the platform refuses it.**
        Measured on the development machine: the first ``set_mode`` that changes
        the flags is dropped -- ``Requested window size: (1600, 900) / New window
        size: (2560, 1440)`` -- and the second, identical call is honoured. So a
        player who switched from borderless to windowed and picked a size saw the
        window stay the size of their desktop, with nothing wrong on screen to
        explain it. Measuring the granted size and asking again is the whole fix,
        and it is what "measured, never assumed" has to mean when the assumption
        can be dropped on the floor.
        """
        asked = self._window_size(spec, monitor)
        surface = self._set_mode(spec, monitor, asked)
        for _ in range(SIZE_ATTEMPTS - 1):
            if surface.get_size() == asked:
                break
            logger.info(
                "The platform granted %s instead of %s; asking again",
                surface.get_size(),
                asked,
            )
            surface = self._set_mode(spec, monitor, asked)
        # Assigned before either step below, because both read ``self.size`` off
        # it and the granted size is what placement clamps against. Assigning it
        # after would work until something replaced the display surface behind
        # us, and then raise an AttributeError on the very first frame -- which
        # is the window-creation frame, with no fallback in reach.
        self.surface = surface
        self._place(spec, monitor)
        self._limit_size()
        return surface

    def _set_mode(
        self, spec: WindowSpec, monitor: Monitor, size: tuple[int, int]
    ) -> pygame.Surface:
        """One ``set_mode`` for this specification, at ``size``.

        Assigned to ``self.surface`` as it goes, so that every caller between this
        and :meth:`_place` sees the current one rather than the previous frame's.
        """
        surface = pygame.display.set_mode(
            size,
            self._flags(spec),
            0,
            self._display_index(spec, monitor),
            1 if spec.vsync else 0,
        )
        self.surface = surface
        return surface

    @staticmethod
    def _display_index(spec: WindowSpec, monitor: Monitor) -> int:
        """The display to open on, validated against the monitor we were given.

        pygame raises rather than clamping, and it raises on the first frame of
        the launch. The ``spec`` is trusted only as a fallback for the case
        where no topology could be read at all -- in which case index 0 is the
        only index that can exist.
        """
        return monitor.index if monitor.index >= 0 else max(0, spec.monitor)

    @staticmethod
    def _mode_for(spec: WindowSpec) -> DisplayMode:
        """AUTO behaves as borderless for flags, so it behaves as borderless here."""
        return spec.mode if spec.mode.is_concrete else DisplayMode.BORDERLESS

    @staticmethod
    def _window_size(spec: WindowSpec, monitor: Monitor) -> tuple[int, int]:
        """The size to ask for, which each mode answers for itself.

        - **Window**: the remembered size if there is one, else as large as fits.
          A starting point and a preference respectively; the player drags it to
          whatever they like and the render target follows.
        - **Borderless**: the remembered size if there is one, else the monitor's
          *usable* size. Not the panel's, because a borderless window that covers
          a taskbar is not borderless, it is overlapping -- measured here as a
          32px panel on a 1080p screen.

          Borderless honours a chosen size because it is a window, not a takeover:
          measured, ``FULLSCREEN | NOFRAME`` at 1600x900 yields a 1600x900
          borderless window that is still positioned and draggable. Treating it
          as always-the-panel would have made the window-size row a lie in this
          mode -- the row says one thing and the window is another.
        - **Fullscreen**: the remembered mode, else ``(0, 0)``, which is how SDL
          is told to use the display's current mode rather than one we made up.
        """
        mode = Stage._mode_for(spec)
        if mode is DisplayMode.FULLSCREEN:
            return Stage._fullscreen_size(spec)
        if spec.size is not None:
            return fit_size(spec.size, monitor)
        if mode is DisplayMode.BORDERLESS:
            return monitor.usable_size
        return opening_size(monitor)

    @staticmethod
    def supported_modes() -> tuple[tuple[int, int], ...]:
        """Every mode the driver reports for this display, largest first.

        The driver's own answer, asked at launch rather than cached: the list is
        what this panel supports right now, and it changes when a cable does. A
        mode that is not in it cannot be honoured, so asking is the only way to
        know before the crash rather than during it.
        """
        try:
            return tuple(sorted(set(pygame.display.list_modes()), reverse=True))
        except pygame.error:
            return ()

    @staticmethod
    def _fullscreen_size(spec: WindowSpec) -> tuple[int, int]:
        """The mode to request in exclusive fullscreen.

        ``(0, 0)`` unless the player chose one, which is how SDL is told to use
        the display's current mode rather than one we made up. A chosen mode is
        checked against the driver and dropped if it is gone: this is the exact
        failure the old resolution catalogue had -- 2560x1440 offered to a
        1366x768 laptop -- except that the list here came from the panel, so the
        only way to reach this branch is a machine that changed after the choice
        was made, and the player's own mode list is not the thing at fault.
        """
        chosen = spec.fullscreen_mode
        if chosen is None:
            return (0, 0)
        modes = Stage.supported_modes()
        if modes and chosen not in modes:
            logger.info("Fullscreen mode %s is no longer supported; using the display's", chosen)
            return (0, 0)
        return chosen

    @staticmethod
    def _flags(spec: WindowSpec) -> int:
        """The SDL flags for a mode.

        Windowed is resizable. It used not to be, on the grounds that a user
        drag would change the viewport the camera culls against -- which was
        true, and stopped being true once the framing became a fixed constant
        in world units. A resized window now changes how large the world is
        *drawn* and nothing else.

        Borderless carries ``NOFRAME``. That is the whole difference from
        fullscreen, and it is what stops a borderless window from asking the
        driver for a mode change: with the flag, the window covers the panel at
        the panel's own resolution, so there is no mode to fail and nothing to
        restore when the laptop switches GPU.

        ``pygame.SCALED`` is gone. It was doing the letterboxing, which the
        render target does itself, and pygame's own documentation calls it an
        experimental API. Dropping it is also why windowed vsync is unreliable:
        SDL only honours the request for a scaled or GL surface.

        Measured on the development machine, and against that last sentence:
        ``set_mode(RESIZABLE, vsync=1)`` reports ``is_vsync() == True`` on
        Wayland with SDL 2.32.10, so windowed vsync does work here and the menu
        reports what the driver actually says rather than assuming.
        """
        mode = Stage._mode_for(spec)
        if mode is DisplayMode.FULLSCREEN:
            return pygame.FULLSCREEN
        if mode is DisplayMode.BORDERLESS:
            # No mode change: a window at the panel's own resolution, with the
            # decoration off. NOFRAME is the whole difference from fullscreen,
            # and it is what stops this asking the driver for a mode change.
            return pygame.FULLSCREEN | pygame.NOFRAME
        return pygame.RESIZABLE

    def _place(self, spec: WindowSpec, monitor: Monitor) -> None:
        """Put the window where the player left it, or centre it.

        A remembered position is honoured when it still lands somewhere the
        player can reach it, and ignored when it does not -- a window on a
        monitor that is no longer attached cannot be dragged back, and the
        player is left with a game they cannot get to.

        **Every mode but exclusive fullscreen is placed**, borderless included.
        Borderless used to be left alone on the grounds that a fullscreen window
        is placed by SDL, and that is true of ``FULLSCREEN`` and false of
        ``FULLSCREEN | NOFRAME``: a borderless window is a real window, measured
        at 1600x900 still positioned and draggable. Leaving it alone had a price:
        ``set_mode``'s display index does **not** move a window that already
        exists (measured, twice in a row on the other display), so picking another
        screen from the menu changed the label, changed nothing else, and left the
        game on the panel the player had just said no to. A screen the menu
        cannot move the window to is a row that cannot be acted on.

        The request is then re-issued until the window is on the monitor we asked
        for. Not the pixels -- a window manager may add its frame to the position
        it reports -- but the *panel*: the exact figure only the game can check is
        which screen the window ended up on.
        """
        if Stage._mode_for(spec) is DisplayMode.FULLSCREEN:
            # SDL puts a real fullscreen window on the display itself and refuses
            # to move it, so asking is at best a no-op.
            return
        window = self._window_handle()
        if window is None:
            return
        granted = self.size
        position = centre_on(monitor, granted)
        if spec.position is not None:
            position = fit_position(spec.position, granted, monitor)
        for attempt in range(PLACE_ATTEMPTS):
            if attempt:
                # The wait is only paid when the previous request did not land,
                # so the common case -- a window that is where it was asked to be
                # -- costs nothing. Measured: three requests issued back to back
                # are all dropped by the same window-manager pass, and the fourth
                # lands 30ms later. A retry that never waits is a retry that never
                # gets its turn.
                pygame.time.wait(PLACE_RETRY_WAIT_MS)
            window.position = position
            # The window manager applies a move asynchronously and answers the
            # question below from where the window *was*, so the queue is pumped
            # before it is asked. Without this a burst of rebuilds reads its own
            # previous request back and decides the platform refused.
            pygame.event.pump()
            if Stage.on_monitor(monitor):
                return
        logger.info(
            "The window did not land on %s (%s); leaving it where the WM put it",
            monitor.name,
            self._reported_position(),
        )

    @staticmethod
    def on_monitor(monitor: Monitor, position: tuple[int, int] | None = None) -> bool:
        """Whether the window sits on ``monitor``.

        The window's top-left corner rather than its whole rectangle, because a
        window larger than the panel is a legitimate thing to ask for and
        refusing to re-place it would be the game overriding a choice the player
        can see.

        With :data:`TITLE_BAR_KEEP` of slack **on the top and left only**. A
        window manager that decorates a window draws the decoration outside the
        client area, so the position it reports is the one that was asked for
        moved *up and to the left* by the frame -- 32px on each axis, measured.
        A check with no slack would re-issue the request three times for a window
        that had arrived, and then log that it had not; a check with slack on the
        bottom and right as well would accept a window a whole frame lower than
        the panel it is supposed to be on.

        ``position`` is read from the platform when not given, and a platform
        that will not say is believed: :attr:`monitor` bounds the answer to a
        coordinate the game cannot invent.
        """
        if position is None:
            try:
                reported: tuple[int, int] = tuple(  # type: ignore[assignment]
                    pygame.display.get_window_position()
                )
            except pygame.error:
                return True
            position = reported
        left, top, width, height = monitor.bounds
        x, y = position
        return (
            left - TITLE_BAR_KEEP[0] <= x < left + width
            and top - TITLE_BAR_KEEP[1] <= y < top + height
        )

    @staticmethod
    def _reported_position() -> tuple[int, int] | str:
        """Where the platform says the window is, or that it will not say.

        For the log on a placement that failed: a failure that crashes the launch
        while describing itself is not a failure the player can do anything with.
        """
        try:
            return tuple(pygame.display.get_window_position())  # type: ignore[return-value]
        except pygame.error:
            return "unknown"

    @staticmethod
    def _window_handle() -> pygame.Window | None:
        """The window behind the display surface, when this build has one.

        Reaching for it is deprecated, and correctly so: ``pygame.display`` and
        ``pygame.Window`` are two APIs the library intends to separate. The
        alternative is not doing the thing at all, and the failure mode of a
        handle that stopped working is a window left where the window manager put
        it -- worse-looking, not broken.
        """
        try:
            return pygame.Window.from_display_module()
        except pygame.error, AttributeError:
            logger.debug("No Window handle; leaving the window where the WM put it")
            return None

    def _limit_size(self) -> None:
        """Refuse a window too small to hold the interface.

        The interface refuses to shrink its text past a floor, so a window
        smaller than that floor is a window the player cannot read the menus in
        and cannot drag back out of. Measured here: at 640x480 only one of the
        five placeable debug panels finds a slot, which is why the panel ladder
        goes to 0.4; the window floor is the same idea one level up.

        Best effort. A window manager that refuses the constraint is a cosmetic
        problem, not a reason to fail the launch.
        """
        window = self._window_handle()
        if window is None:
            return
        try:
            window.minimum_size = MIN_WINDOW
        except pygame.error, AttributeError:
            logger.debug("The platform refused a minimum window size")

    def __repr__(self) -> str:
        return (
            f"Stage({Stage._mode_for(self.spec).value}, monitor={self.monitor.index}, "
            f"size={self.size})"
        )


__all__ = [
    "Stage",
    "WindowSpec",
    "TITLE_BAR_KEEP",
    "SIZE_ATTEMPTS",
    "PLACE_ATTEMPTS",
    "PLACE_RETRY_WAIT_MS",
]
