"""The fixed-size surface the whole game draws into."""

import pygame

from .framing import DEFAULT_FRAMING, Framing

#: Render scales offered to the player. Integers only: the art is authored at
#: one pixel per world unit and is scaled once when loaded, and an integer
#: factor reproduces every source pixel exactly.
RENDER_SCALES = (1, 2, 3)

#: The scale the game starts with.
#:
#: Measured by ``tests/benchmarks/render_benchmark.py`` on the registered
#: level: the world draw costs 2.19ms at 1x, 4.22ms at 2x and 7.77ms at 3x, so
#: the scale is not free -- the target is that many times the pixels. It is the
#: default anyway because it is the one that keeps sprites crisp, and because
#: the cost that actually decides whether a frame fits is the presentation,
#: which this does not change.
#:
#: The measured crossover, for the video menu's hint: smooth scaling plus a 2x
#: draw is 60% of a 60Hz frame at 1920x1080, 70% at 2560x1440, 82% at 3440x1440
#: and 105% at 3840x2160 -- over budget. Past 1440p, Smoothing off or Render
#: scale 1x brings 4K back to 56%.
DEFAULT_RENDER_SCALE = 2


def render_scale_for(size: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> int:
    """The smallest offered scale whose target covers a window of ``size``.

    A render target smaller than the window it is shown in is scaled *up* on
    the way out, which costs the fill rate of the larger surface and returns a
    blurrier image than a smaller target would have drawn. So the default
    follows the machine, the way the window size already does through
    ``SizeMode.AUTO``: 1x on a 1366x768 laptop, 2x at 1440p, 3x in borderless
    on a 4K panel -- capped at the top of ``RENDER_SCALES``, which is where 4K
    starts being scaled up again.

    The argument is the *window*, not the desktop, so a windowed game on a 4K
    screen still gets 2x for a 2560x1440 window. Pass ``(0, 0)`` when the
    desktop is unknown, which headless runs are, and this answers
    ``DEFAULT_RENDER_SCALE`` -- today's behaviour, unchanged.

    This is a default, not a rule: ``Render scale`` in the video menu overrides
    it, and a stored setting keeps its value even when the desktop it was
    chosen on is gone.
    """
    if size[0] <= 0 or size[1] <= 0:
        return DEFAULT_RENDER_SCALE
    for scale in RENDER_SCALES:
        target = framing.viewport_size(scale)
        if target[0] >= size[0] and target[1] >= size[1]:
            return scale
    return RENDER_SCALES[-1]


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

    def fill(self, color: tuple[int, int, int]) -> None:
        """Erase the whole surface to ``color``."""
        self.surface.fill(color)

    def __repr__(self) -> str:
        return f"Viewport({self.size[0]}x{self.size[1]}, scale={self.scale})"
