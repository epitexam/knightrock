"""Which move each attack button throws: the blade or the body, high or low.

Two buttons, the slash and the beat, each thrown high or low: the low stance
is Down held on the ground. What a press throws depends, most specific first,
on what the fighter is doing:

1. a downed enemy within reach turns a low slash into the stab that ends it;
2. a running move continues its chain with the press (``follow_ups`` in
   ``attacks.json``);
3. in the air, the slash and the dive;
4. otherwise, the first link of the press's chain.

The shot is a third button, thrown the same high or low.

The throw, the death blow and the charged moves are not presses: the player
starts them itself (``Player``), from a stunned foe, a prompt, and a button
held (:data:`CHARGES`).
"""

from dataclasses import dataclass

from src.combat.frame_data import AttackButton, AttackDefinition, MoveId, Stance, move_id
from src.core.input.input_actions import InputAction

#: The two attack buttons, high and low.
PRESSES: dict[tuple[InputAction, bool], AttackButton] = {
    (InputAction.ATTACK_1, False): AttackButton.SLASH_HIGH,
    (InputAction.ATTACK_1, True): AttackButton.SLASH_LOW,
    (InputAction.ATTACK_2, False): AttackButton.BEAT_HIGH,
    (InputAction.ATTACK_2, True): AttackButton.BEAT_LOW,
    (InputAction.SHOOT, False): AttackButton.SHOOT,
    (InputAction.SHOOT, True): AttackButton.SHOOT,
}

#: The first link of each chain, on the ground.
GROUND_STARTERS: dict[AttackButton, MoveId] = {
    AttackButton.SLASH_HIGH: move_id("slash_high_1"),
    AttackButton.SLASH_LOW: move_id("slash_low_1"),
    AttackButton.BEAT_HIGH: move_id("punch_1"),
    AttackButton.BEAT_LOW: move_id("kick_1"),
    AttackButton.SHOOT: move_id("shot"),
}

#: In the air: the slash, and the beat dives.
AIR_STARTERS: dict[AttackButton, MoveId] = {
    AttackButton.SLASH_HIGH: move_id("air_slash"),
    AttackButton.SLASH_LOW: move_id("air_slash"),
    AttackButton.BEAT_HIGH: move_id("air_kick"),
    AttackButton.BEAT_LOW: move_id("air_kick"),
    AttackButton.SHOOT: move_id("air_shot"),
}

STAB = move_id("stab")
CHARGED_SLASH = move_id("charged_slash")
CHARGED_SLASH_FULL = move_id("charged_slash_full")
CHARGED_KICK = move_id("charged_kick")
SHOT = move_id("shot")
PIERCING_SHOT = move_id("piercing_shot")
DEATH_BLOW = move_id("death_blow")
THROW = move_id("throw")

#: The moves that cut with the blade: each costs battery and is weak without it.
SLASHES: frozenset[MoveId] = frozenset(
    {
        *(move_id(f"slash_high_{n}") for n in range(1, 5)),
        *(move_id(f"slash_low_{n}") for n in range(1, 5)),
        move_id("air_slash"),
        STAB,
        CHARGED_SLASH,
        CHARGED_SLASH_FULL,
    }
)

#: The shots: each spends ``Battery.SHOT_COST``, and an empty battery fires none.
SHOTS: frozenset[MoveId] = frozenset({SHOT, move_id("air_shot"), PIERCING_SHOT})


@dataclass(frozen=True)
class Charge:
    """What a button held charges, and what it becomes once the charge is full."""

    move: MoveId
    full: MoveId | None = None


#: The charge of each attack button. The slash and the shot have two tiers:
#: let go early, the charged move, harder with the time held; held to the end,
#: a stronger move of its own. The body's charge has one.
CHARGES: dict[InputAction, Charge] = {
    InputAction.ATTACK_1: Charge(CHARGED_SLASH, CHARGED_SLASH_FULL),
    InputAction.ATTACK_2: Charge(CHARGED_KICK),
    InputAction.SHOOT: Charge(SHOT, PIERCING_SHOT),
}


@dataclass(frozen=True)
class MoveContext:
    """What the fighter is doing when a button is pressed, as far as the move cares."""

    stance: Stance
    running: AttackDefinition | None = None
    """The move in progress, whose chain the press may continue."""
    downed_in_reach: bool = False
    """A downed enemy lies within reach in front: a low slash stabs it."""


def press_for(action: InputAction, low: bool) -> AttackButton | None:
    """The press ``action`` makes in the high or the low stance, or ``None``."""
    return PRESSES.get((action, low))


def resolve_move(press: AttackButton, context: MoveContext) -> MoveId | None:
    """The move ``press`` throws in ``context``, or ``None`` if it has none there."""
    if context.stance is Stance.WALL:
        return None
    if (
        context.stance is Stance.GROUND
        and press is AttackButton.SLASH_LOW
        and context.downed_in_reach
    ):
        return STAB
    if context.running is not None:
        follow_up = context.running.follow_up(press)
        if follow_up is not None:
            return follow_up
    if context.stance is Stance.AIR:
        return AIR_STARTERS.get(press)
    return GROUND_STARTERS.get(press)
