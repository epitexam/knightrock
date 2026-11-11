"""The window: its size, its position, fullscreen and vsync.

The only module that calls ``set_mode``; everything else draws into a
``Viewport``. One mode: a ``RESIZABLE`` window, sized by the player and placed
by the window manager. Fullscreen is the desktop kind, with no mode change --
a real mode change is what blacks out a hybrid-GPU laptop.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pygame

from .monitors import (
    MIN_WINDOW,
    Monitor,
    centre_on,
    fit_size,
    opening_size,
    sits_within,
)

logger = logging.getLogger(__name__)

#: How many times a size is asked for before a refusal is believed: the
#: platform sometimes grants another size once and honours the same request
#: the second time.
SIZE_ATTEMPTS = 2

#: The window's flags. No ``SCALED``: the render target does the letterboxing.
WINDOW_FLAGS = pygame.RESIZABLE


@dataclass(frozen=True)
class WindowSpec:
    """What the player asked for, before the platform has its say.

    ``size`` is clamped to the monitor it opens on; ``None`` lets the machine
    decide (first launch, reset).
    """

    vsync: bool = False
    size: tuple[int, int] | None = None
    #: Desktop fullscreen: the window covers its screen without a mode change.
    #: ``size`` is still the windowed size, the one it returns to.
    fullscreen: bool = False


class Stage:
    """The OS window the game is presented in.

    The granted size is read back off the surface, never trusted from the
    request. Placement uses the monitor's real origin from
    :mod:`src.core.display.sdl_probe`.
    """

    def __init__(self, spec: WindowSpec, monitor: Monitor) -> None:
        self.spec = spec
        self.monitor = monitor
        #: Whether the window covers its screen, and the size it had before.
        self.fullscreen = False
        self.windowed_size: tuple[int, int] | None = None
        self.surface = self._create(spec, monitor)

    @property
    def size(self) -> tuple[int, int]:
        """The window's granted size, read back from the surface."""
        return self.surface.get_size()

    def rebuild(self, spec: WindowSpec, monitor: Monitor) -> pygame.Surface:
        """Recreate the window for a new specification and return its surface.

        All or nothing: if ``set_mode`` fails (vsync refused, screen gone), the
        previous state is restored and the error raised for the caller.
        """
        previous = (self.spec, self.monitor, self.surface, self.fullscreen, self.windowed_size)
        try:
            self.spec = spec
            self.monitor = monitor
            self.fullscreen = False
            self.surface = self._create(spec, monitor)
        except Exception:
            (self.spec, self.monitor, self.surface, self.fullscreen, self.windowed_size) = previous
            raise
        return self.surface

    def set_fullscreen(self, on: bool) -> pygame.Surface:
        """Cover the screen, or go back to the window, without a mode change.

        The windowed size is kept: the window returns to it, and the next launch
        opens at it.
        """
        if on == self.fullscreen:
            return self.surface
        window = self._window_handle()
        if window is None:
            raise pygame.error("This platform has no window to make fullscreen")
        if on:
            self.windowed_size = self.size
            window.set_fullscreen(desktop=True)
        else:
            window.set_windowed()
        self.fullscreen = on
        self.surface = pygame.display.get_surface() or self.surface
        return self.surface

    def _create(self, spec: WindowSpec, monitor: Monitor) -> pygame.Surface:
        """Open the window at the asked size (asking again once if refused), then place it.

        Placed after sizing, so the placement works against the granted size.
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
        # Before placing: placement reads ``self.size``.
        self.surface = surface
        self._place(spec, monitor)
        self._limit_size()
        if spec.fullscreen:
            self.set_fullscreen(True)
            self.windowed_size = asked
        return self.surface

    def _set_mode(
        self, spec: WindowSpec, monitor: Monitor, size: tuple[int, int]
    ) -> pygame.Surface:
        """One ``set_mode`` at ``size``, kept in ``self.surface`` straight away."""
        surface = pygame.display.set_mode(
            size,
            WINDOW_FLAGS,
            0,
            monitor.index,
            1 if spec.vsync else 0,
        )
        self.surface = surface
        return surface

    @staticmethod
    def _window_size(spec: WindowSpec, monitor: Monitor) -> tuple[int, int]:
        """The chosen size fitted to the monitor and raised to ``MIN_WINDOW``,
        or the opening size when nothing was chosen."""
        if spec.size is not None:
            return fit_size(spec.size, monitor)
        return opening_size(monitor)

    def _place(self, spec: WindowSpec, monitor: Monitor) -> None:
        """Keep the window where it is if it still fits its screen; centre it otherwise.

        Re-centring on every size change made the window jump across a
        two-screen desk.
        """
        window = self._window_handle()
        if window is None:
            return
        try:
            position = window.position
            current = (int(position[0]), int(position[1]))
        except pygame.error, AttributeError:
            logger.debug("No window position readable; centring")
            window.position = centre_on(monitor, self.size)
            return
        if sits_within(current, monitor, self.size):
            return
        window.position = centre_on(monitor, self.size)

    @staticmethod
    def _window_handle() -> pygame.Window | None:
        """The window behind the display surface, when this build has one.

        Deprecated in pygame-ce; without it the window stays where the window
        manager put it, which is cosmetic.
        """
        try:
            return pygame.Window.from_display_module()
        except pygame.error, AttributeError:
            logger.debug("No Window handle; leaving the window where the WM put it")
            return None

    def _limit_size(self) -> None:
        """Ask for ``MIN_WINDOW`` as the minimum size. Best effort."""
        window = self._window_handle()
        if window is None:
            return
        try:
            window.minimum_size = MIN_WINDOW
        except pygame.error, AttributeError:
            logger.debug("The platform refused a minimum window size")

    def __repr__(self) -> str:
        return f"Stage(monitor={self.monitor.index}, size={self.size})"


__all__ = [
    "Stage",
    "WindowSpec",
    "SIZE_ATTEMPTS",
]
