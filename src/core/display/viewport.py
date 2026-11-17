"""The surface every draw call in the game targets.

Its size is the letterbox rectangle, so it changes when the window does and for
no other reason. The density is read back off it rather than configured, so the
surface and the transform drawing onto it cannot disagree.
"""

import pygame

from .framing import DEFAULT_FRAMING, Framing
from .letterbox import density_for


class Viewport:
    """The pixel surface every draw call targets.

    ``size`` should be a letterbox rectangle for ``framing``; its only producer
    is :class:`~src.core.display.presentation.Presentation`.
    """

    def __init__(
        self,
        framing: Framing = DEFAULT_FRAMING,
        size: tuple[int, int] = (2, 2),
        *,
        convert: bool = False,
    ) -> None:
        self.framing = framing
        self.size = (max(1, int(size[0])), max(1, int(size[1])))
        #: Target pixels per world unit, read off ``size`` rather than chosen.
        self.density = density_for(self.size, framing)
        self.surface = pygame.Surface(self.size)
        # Converted, the 1:1 blit onto the window is a plain copy. Needs a
        # display, so a headless caller asking for it is not an error.
        if convert and pygame.display.get_surface() is not None:
            self.surface = self.surface.convert()

    @property
    def rect(self) -> pygame.Rect:
        """The viewport as a rect, for the drawing code that wants one."""
        return self.surface.get_rect()

    def fill(self, color: tuple[int, int, int]) -> None:
        """Erase the whole surface to ``color``."""
        self.surface.fill(color)

    def __repr__(self) -> str:
        return f"Viewport({self.size[0]}x{self.size[1]}, density={self.density:.3f})"
