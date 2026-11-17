"""The framing: how much of the world the player is allowed to see.

A fixed answer in world units, and the only display quantity the simulation
reads. The window changes how large the world is *drawn*, never how much of it
is *shown* -- when the camera used the window's size, a bigger window revealed
more of the level.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Framing:
    """The visible slice of the world, in world units. Immutable: a gameplay contract."""

    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("A framing needs a strictly positive size")

    @property
    def size(self) -> tuple[float, float]:
        """The framing as a size tuple, for the APIs that want one."""
        return (self.width, self.height)

    @property
    def aspect(self) -> float:
        """Width over height: the shape of the visible world."""
        return self.width / self.height

    def is_smaller_than(self, world_size: tuple[float, float]) -> bool:
        """Whether this framing shows less than ``world_size`` on both axes.

        Both: a framing narrower but taller than a level still shows all of it.
        ``tests/unit/test_framing_contract.py`` checks every ``.tmx``.
        """
        return self.width < world_size[0] and self.height < world_size[1]


#: The gameplay framing: 16:9, and smaller than every level on both axes. How
#: many pixels a world unit takes is read off the render target
#: (:func:`src.core.display.letterbox.density_for`), not decided here.
DEFAULT_FRAMING = Framing(1152.0, 648.0)
