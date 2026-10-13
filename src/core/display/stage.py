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


class Stage:
    """The OS window the game is presented in.

    Two rules earn their keep here:

    * **The surface is measured, never assumed.** The size actually granted is
      read back off the surface rather than trusted from the request, because
      with high-DPI windows the two differ and every layout downstream would be
      quietly wrong.
    * **Placement is computed from real display bounds, or handed to SDL.**
      Both, in that order. Centring needs the monitor's origin on the virtual
      desktop, which :mod:`src.core.display.sdl_probe` now supplies; when it
      cannot, the position is left to ``WINDOWPOS_CENTERED`` rather than guessed
      at, because a wrong guess puts the window on the other monitor.
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
        """
        surface = pygame.display.set_mode(
            self._window_size(spec, monitor),
            self._flags(spec),
            0,
            self._display_index(spec, monitor),
            1 if spec.vsync else 0,
        )
        # Assigned before either step below, because both read ``self.size`` off
        # it and the granted size is what placement clamps against. Assigning it
        # after would work until something replaced the display surface behind
        # us, and then raise an AttributeError on the very first frame -- which
        # is the window-creation frame, with no fallback in reach.
        self.surface = surface
        self._place(spec, monitor)
        self._limit_size()
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
        - **Borderless**: the monitor's *usable* size. Not the panel's, because a
          borderless window that covers a taskbar is not borderless, it is
          overlapping -- measured here as a 32px panel on a 1080p screen.
        - **Fullscreen**: the remembered mode, else ``(0, 0)``, which is how SDL
          is told to use the display's current mode rather than one we made up.
        """
        mode = Stage._mode_for(spec)
        if mode is DisplayMode.FULLSCREEN:
            return (0, 0)
        if mode is DisplayMode.BORDERLESS:
            return monitor.usable_size
        if spec.size is not None:
            return fit_size(spec.size, monitor)
        return opening_size(monitor)

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
        if mode is DisplayMode.BORDERLESS:
            return pygame.FULLSCREEN | pygame.NOFRAME
        if mode is DisplayMode.FULLSCREEN:
            return pygame.FULLSCREEN
        return pygame.RESIZABLE

    def _place(self, spec: WindowSpec, monitor: Monitor) -> None:
        """Put the window where the player left it, or centre it.

        A remembered position is honoured when it still lands somewhere the
        player can reach it, and ignored when it does not -- a window on a
        monitor that is no longer attached cannot be dragged back, and the
        player is left with a game they cannot get to.

        Only window mode is placed at all. SDL puts a fullscreen window on the
        display itself and refuses to move it, so asking is at best a no-op.
        """
        if Stage._mode_for(spec) is not DisplayMode.WINDOW:
            return
        granted = self.size
        try:
            window = pygame.Window.from_display_module()
        except pygame.error, AttributeError:
            # No Window handle in this build. Leave placement to the window
            # manager, which gets it right more often than a guess would.
            logger.debug("No Window handle; leaving the window where the WM put it")
            return

        position: tuple[int, int] | None = None
        if spec.position is not None:
            position = fit_position(spec.position, granted, monitor)
        if position is None:
            position = centre_on(monitor, granted)
        window.position = position

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
        try:
            window = pygame.Window.from_display_module()
        except pygame.error, AttributeError:
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


__all__ = ["Stage", "WindowSpec", "TITLE_BAR_KEEP"]
