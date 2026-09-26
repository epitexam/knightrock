"""Who picks the window size: the player, or the machine.

``AUTO`` is not a "reset to default" marker. It means *re-evaluate on every
launch*, which is what makes the game adapt when the machine changes under it:
dock the laptop, plug a 4K monitor in, run the game somewhere else. A size the
player chose by hand is honoured; a size the game chose is only ever honoured
while it still makes sense.
"""

from enum import StrEnum


class SizeMode(StrEnum):
    """Whether the stored window size is a decision or a guess."""

    AUTO = "auto"
    MANUAL = "manual"
