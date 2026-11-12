"""Which move each attack button throws: posture, chain, dash, dive and riposte.

This used to be one ternary. ``ATTACK_1`` resolved to ``light_attack`` or
``air_attack`` on whether the fighter had a floor, and every other button named
its move outright -- so a crouching fighter got ``light_attack``, the standing
move, from a collider 40% shorter, and nothing in the code could say otherwise
because there was nowhere to say it.

``BUTTON_MOVES`` is that answer, per button and per posture. A button with no
entry for the fighter's current posture has no move there: not an error, not a
fallback to the standing version, just nothing -- which is what makes a crouch a
real restriction instead of a costume.
"""

from dataclasses import dataclass

from src.combat.frame_data import AttackButton, AttackDefinition, MoveId, Stance, move_id
from src.core.input.input_actions import InputAction

#: Stance to move, per button, with nothing else going on. Two attack buttons,
#: light and heavy: the variety comes from the chains each move declares in
#: ``attacks.json`` (``follow_ups``), from the dash and from Down in the air, not
#: from more buttons. The special is ground-only: it is a 110-frame commitment.
BUTTON_MOVES: dict[InputAction, dict[Stance, MoveId]] = {
    InputAction.ATTACK_1: {
        Stance.GROUND: move_id("light_attack"),
        Stance.CROUCH: move_id("crouch_slash"),
        Stance.AIR: move_id("air_attack"),
    },
    InputAction.ATTACK_2: {
        Stance.GROUND: move_id("heavy_attack"),
        Stance.CROUCH: move_id("crouch_sweep"),
        Stance.AIR: move_id("air_rise"),
    },
    InputAction.SPECIAL_ATTACK: {Stance.GROUND: move_id("special_attack")},
}

#: The two attack buttons, as the chains in ``attacks.json`` name them.
ATTACK_BUTTONS: dict[InputAction, AttackButton] = {
    InputAction.ATTACK_1: AttackButton.LIGHT,
    InputAction.ATTACK_2: AttackButton.HEAVY,
}

#: The guaranteed blow after a parry, on either button.
RIPOSTE = move_id("riposte")
#: The light button out of a dash.
DASH_ATTACK = move_id("dash_attack")
#: In the air with Down held: the heavy button dives.
DIVE_MOVES: dict[InputAction, MoveId] = {InputAction.ATTACK_2: move_id("air_sweep")}


@dataclass(frozen=True)
class MoveContext:
    """What the fighter is doing when a button is pressed, as far as the move cares."""

    stance: Stance
    running: AttackDefinition | None = None
    """The move in progress, whose chain the button may continue."""
    dashing: bool = False
    """Mid-dash or just out of one: the light button lunges."""
    diving: bool = False
    """Airborne with Down held: the heavy button dives."""
    riposte: bool = False
    """Just parried: either button ripostes."""


def resolve_move(action: InputAction, context: MoveContext) -> MoveId | None:
    """The move ``action`` throws in ``context``, or ``None`` if it has none.

    Most specific first: a riposte, then the next link of the running chain,
    then the dash and dive variants, then the button's move for the posture.
    ``None`` is a real answer, as in :func:`move_for_button`.
    """
    button = ATTACK_BUTTONS.get(action)
    if button is not None:
        if context.riposte:
            return RIPOSTE
        if context.running is not None:
            follow_up = context.running.follow_up(button)
            if follow_up is not None:
                return follow_up
        if context.dashing and button is AttackButton.LIGHT and context.stance is Stance.GROUND:
            return DASH_ATTACK
        if context.diving and action in DIVE_MOVES:
            return DIVE_MOVES[action]
    return BUTTON_MOVES.get(action, {}).get(context.stance)


def move_for_button(action: InputAction, stance: Stance) -> MoveId | None:
    """The move ``action`` throws from ``stance`` with nothing else going on."""
    return resolve_move(action, MoveContext(stance))
