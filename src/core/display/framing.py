"""The framing: how much of the world the player is allowed to see.

Why this module exists
----------------------
The game used to answer "how much world is visible" from the *window*: the
camera was built with the window's pixel dimensions and a fixed zoom, so the
visible world was a free variable of a video setting. Measured on the level
actually registered for play (2560x1920 world pixels), the reveal went from
34% of the height at the smallest preset to 60% at the largest, and on the
unregistered 40x15 levels a high enough preset revealed a whole level, height
included. A player could see more of the level by opening the video menu.

``Framing`` closes that door. It is the single fixed answer, expressed in world
units, and it is the only display quantity the simulation is allowed to read.
The window can then be whatever the player or the desktop imposes: it changes
how large the world is *drawn*, never how much of it is *shown*.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Framing:
    """The visible slice of the world, in world units.

    Immutable on purpose: this is a gameplay contract, and a contract that can
    be edited in place mid-session is not one.
    """

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

        Both axes are required, and that is the whole point. A framing narrower
        than a level but taller than it still puts the entire level on screen,
        so "smaller" has to mean smaller in every direction before the suspense
        this framing exists for is actually there.

        ``tests/unit/test_framing_contract.py`` runs this over every ``.tmx``
        in the level folder.
        """
        return self.width < world_size[0] and self.height < world_size[1]

    def viewport_size(self, scale: int) -> tuple[int, int]:
        """The pixel size of the render target for an integer ``scale``.

        The scale is an integer because the art is authored at one pixel per
        world unit and is rescaled once when it is loaded. An integer factor
        reproduces every pixel exactly; a fractional one does not.
        """
        if scale < 1:
            raise ValueError("The render scale must be at least 1")
        return (round(self.width * scale), round(self.height * scale))


#: The gameplay framing.
#:
#: Chosen against the levels rather than for a round number: 1152x648 shows
#: 45% of the width and 34% of the height of the registered level, and stays
#: narrower *and* shorter than every ``.tmx`` in the folder, so no level can
#: ever be taken in at once. It is also 16:9, matching most displays, which
#: keeps the letterbox bars small.
DEFAULT_FRAMING = Framing(1152.0, 648.0)
