"""The window: mode, size, position and vsync.

Deliberately the only module in the game that calls ``set_mode``. Everything
else draws into a ``Viewport`` and never learns that a window exists.
"""

import logging
from dataclasses import dataclass

import pygame

from . import detection
from .mode import DisplayMode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowSpec:
    """What the player asked for, before the desktop has its say.

    A plain value rather than ``UserSettings``, so this module stays free of
    the application layer and can be driven straight from a test.
    """

    width: int
    height: int
    mode: DisplayMode = DisplayMode.BORDERLESS
    vsync: bool = False


class Stage:
    """The OS window the game is presented in.

    Two rules earn their keep here:

    * **The surface is measured, never assumed.** The size actually granted is
      read back off the surface rather than trusted from the request, because
      with high-DPI windows the two differ and every layout downstream would be
      quietly wrong.
    * **The window is re-centred after every rebuild.** Changing resolution or
      switching in and out of fullscreen moves the window, and left alone it
      stays wherever the window manager dropped it -- which is how a window
      ends up one monitor away from the one the game is on.
    """

    def __init__(
        self,
        spec: WindowSpec,
        desktop: tuple[int, int] | None = None,
    ) -> None:
        self.spec = spec
        self.surface = self._create(spec, desktop)

    @property
    def size(self) -> tuple[int, int]:
        """The window's granted size, read back from the surface."""
        return self.surface.get_size()

    def rebuild(
        self,
        spec: WindowSpec,
        desktop: tuple[int, int] | None = None,
    ) -> pygame.Surface:
        """Recreate the window for a new specification and return its surface."""
        self.spec = spec
        self.surface = self._create(spec, desktop)
        return self.surface

    def _create(
        self,
        spec: WindowSpec,
        desktop: tuple[int, int] | None,
    ) -> pygame.Surface:
        resolved = detection.desktop_size() if desktop is None else desktop
        surface = pygame.display.set_mode(
            self._window_size(spec, resolved),
            self._flags(spec),
            0,
            0,  # display index: the primary screen, always (see detection)
            1 if spec.vsync else 0,
        )
        # Measured, not requested: see the class docstring.
        self._recenter(self._mode_for(spec))
        return surface

    @staticmethod
    def _mode_for(spec: WindowSpec) -> DisplayMode:
        """AUTO behaves as borderless for flags, so it behaves as borderless here."""
        return spec.mode if spec.mode.is_concrete else DisplayMode.BORDERLESS

    @staticmethod
    def _window_size(spec: WindowSpec, desktop: tuple[int, int]) -> tuple[int, int]:
        """The size to ask for, which is not always the size the player chose.

        Borderless means *the desktop's* size, whatever is in the settings. That
        is the point of the mode: a window that already matches the screen
        cannot be the wrong shape.
        """
        if spec.mode is DisplayMode.BORDERLESS and desktop[0] > 0 and desktop[1] > 0:
            return desktop
        return (max(1, spec.width), max(1, spec.height))

    @staticmethod
    def _flags(spec: WindowSpec) -> int:
        """The SDL flags for a mode.

        Windowed is resizable. It used not to be, on the grounds that a user
        drag would change the viewport the camera culls against -- which was
        true, and stopped being true once the framing became a fixed constant
        in world units. A resized window now changes how large the world is
        drawn and nothing else.

        ``pygame.SCALED`` is gone. It was doing the letterboxing, which the
        render target does itself, and pygame's own documentation calls it an
        experimental API. Dropping it is also why windowed vsync is unreliable:
        SDL only honours the request for a scaled or GL surface.
        """
        if spec.mode is DisplayMode.BORDERLESS:
            return pygame.FULLSCREEN
        if spec.mode is DisplayMode.FULLSCREEN:
            return pygame.FULLSCREEN
        return pygame.RESIZABLE

    @staticmethod
    def _recenter(mode: DisplayMode) -> None:
        """Hand the placement to SDL, which knows where the displays are.

        This used to compute the position itself, from the assumption that the
        primary display sits at the origin of the virtual desktop. That is the
        Windows and macOS convention, and it is **false** on a Linux desktop
        whose primary is not the leftmost monitor. Measured on such a machine --
        two displays, primary 2560x1440 sitting at origin (1920, 0) -- the
        arithmetic produced x=192 and put the window on the *other* monitor,
        which is worse than not placing it at all.

        ``pygame.Window.position`` accepts ``WINDOWPOS_CENTERED``, and SDL
        resolves that against the display the window is actually on. The
        module-level ``pygame.display.set_window_position`` refuses the constant
        ("position must be two numbers"), which is why this goes through the
        ``Window`` handle.

        Reaching the ``Window`` handle of a window created by
        ``display.set_mode`` is deprecated -- pygame warns, correctly, that the
        two APIs will eventually separate. The warning is left visible rather
        than suppressed, and the failure mode is the ``except`` below: if the
        call ever stops working, the window is left where the window manager put
        it, which is a worse-looking outcome and not a broken one.

        A fullscreen window is left alone: SDL places it on the display itself
        and refuses to move it, so asking is at best a no-op.
        """
        if mode is not DisplayMode.WINDOW:
            return
        try:
            pygame.Window.from_display_module().position = pygame.WINDOWPOS_CENTERED
        except pygame.error, AttributeError:
            # No usable Window class in this build. Leave the placement to the
            # window manager, which gets it right more often than a guess
            # from us would.
            logger.debug("No Window handle; leaving the window where the WM put it")
