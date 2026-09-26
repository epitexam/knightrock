"""The fixed-size surface the whole game draws into."""

import pygame

from .framing import DEFAULT_FRAMING, Framing

#: Render scales offered to the player. Integers only: the art is authored at
#: one pixel per world unit and is scaled once when loaded, and an integer
#: factor reproduces every source pixel exactly.
RENDER_SCALES = (1, 2, 3)

#: The scale the game starts with.
#:
#: Measured on the playable level: the world draw costs 1.31ms at 1440x900, and
#: a 2x viewport (2304x1296) puts it around 2.5ms, which is affordable against
#: a 16.7ms frame and keeps the sprites crisp on a large display. Scale 1 is
#: the performance option. Chosen here, confirmed by
#: ``tests/benchmarks/render_benchmark.py``.
DEFAULT_RENDER_SCALE = 2


class Viewport:
    """The pixel surface every draw call in the game targets.

    Its size is ``framing * scale`` and it never changes. That single fact is
    what makes the rest of the interface work: menus, HUD, debug panels and
    world overlays are all laid out against a constant size, so they are laid
    out the same way whatever the window ends up being. The window only
    decides how the finished frame is scaled on its way to the screen, which is
    ``Presentation``'s job and nobody else's.

    Note what the fixity does *not* buy: the layout is constant, but the size
    the player ends up looking at still follows the window, since the whole
    surface is scaled on the way out. Interface scale is the manual lever.
    """

    def __init__(
        self,
        framing: Framing = DEFAULT_FRAMING,
        scale: int = DEFAULT_RENDER_SCALE,
        *,
        convert: bool = False,
    ) -> None:
        self.framing = framing
        self.scale = scale
        self.size = framing.viewport_size(scale)
        self.surface = pygame.Surface(self.size)
        if convert:
            self.surface = self.surface.convert()

    @property
    def rect(self) -> pygame.Rect:
        """The viewport as a rect, for the drawing code that wants one."""
        return self.surface.get_rect()

    @property
    def size_in_world_units(self) -> tuple[float, float]:
        """How much world the surface shows: the framing, by construction."""
        return self.framing.size

    def fill(self, color: tuple[int, int, int]) -> None:
        """Erase the whole surface to ``color``."""
        self.surface.fill(color)

    def __repr__(self) -> str:
        return f"Viewport({self.size[0]}x{self.size[1]}, scale={self.scale})"
