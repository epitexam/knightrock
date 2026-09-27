"""The surface every draw call in the game targets.

Its size is the window's letterbox rectangle, so it changes when the window
does and for no other reason. That single fact is what makes the rest of the
interface work: the world, the HUD, the menus and the debug panels are all laid
out against it, and the density of pixels is read back off it rather than
configured, so a surface and the transform that draws onto it cannot disagree
about how big a world unit is.

Nothing here decides what the picture should look like on a given display. The
window manager resizes the window, the letterbox follows
(:mod:`src.core.display.letterbox`), and this surface follows the letterbox.
"""

import pygame

from .framing import DEFAULT_FRAMING, Framing
from .letterbox import density_for


class Viewport:
    """The pixel surface every draw call in the game targets.

    ``size`` is in pixels and is expected to be a letterbox rectangle for
    ``framing``; it is not checked here because the only producer is
    :class:`~src.core.display.presentation.Presentation`, which is the one
    component allowed to reconcile a window with a target. What *is* checked is
    the consequence -- :attr:`density` -- since a target that does not match the
    framing at one density is a wiring mistake, and a refusal is cheaper than a
    frame drawn at a density nobody asked for.
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
        # Converting is what makes the 1:1 blit onto the window a memcpy
        # instead of a per-pixel format conversion. It needs a display to exist
        # at all, so a headless caller asking for it is not an error.
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
