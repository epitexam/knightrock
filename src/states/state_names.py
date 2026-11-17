"""The state vocabulary other systems ask about, in one place.

The physics, the combat resolver and the renderer ask an entity whether it is
dashing, flying in knockback or dizzy. :class:`StateName` is the canonical set
of names those questions and the state machines use; the ``Final`` aliases below
keep the old import sites working while giving them one typed source.

``StrEnum`` keeps every value identical to the bare string it replaces, so
snapshots and goldens are unchanged.
"""

from enum import StrEnum
from typing import Final


class StateName(StrEnum):
    """Every state name the game can be in, across both fighters."""

    IDLE = "idle"
    WALK_SLOW = "walk_slow"
    WALK = "walk"
    RUN = "run"
    TURN = "turn"
    JUMP = "jump"
    FALL = "fall"
    WALL_SLIDE = "wall_slide"
    ATTACK = "attack"
    GUARD = "guard"
    HURT = "hurt"
    DASH = "dash"
    STAGGER = "stagger"
    CHARGE = "charge"
    RECHARGE = "recharge"
    PROMPT = "prompt"
    KNOCKBACK = "knockback"
    DIZZY = "dizzy"
    PATROL = "patrol"
    CHASE = "chase"
    DOWNED = "downed"
    DOOMED = "doomed"
    LEDGE = "ledge"


DASH: Final[StateName] = StateName.DASH
KNOCKBACK: Final[StateName] = StateName.KNOCKBACK
STAGGER: Final[StateName] = StateName.STAGGER
DIZZY: Final[StateName] = StateName.DIZZY
DOWNED: Final[StateName] = StateName.DOWNED
DOOMED: Final[StateName] = StateName.DOOMED
