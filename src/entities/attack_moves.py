"""Which move each attack button throws, from which posture.

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

from src.combat.attack_data import move_id
from src.combat.frame_data import MoveId, Stance
from src.core.input.input_actions import InputAction

#: Stance to move, per button. The special is ground-only: it is a 110-frame
#: commitment, and letting it come out of a crouch would trade the posture's
#: whole purpose -- a fighter went down to be hard to hit, and then stood still
#: for two seconds doing it on purpose.
BUTTON_MOVES: dict[InputAction, dict[Stance, MoveId]] = {
    InputAction.ATTACK_1: {
        Stance.GROUND: move_id("light_attack"),
        Stance.CROUCH: move_id("crouch_slash"),
        Stance.AIR: move_id("air_attack"),
    },
    InputAction.ATTACK_2: {
        Stance.GROUND: move_id("heavy_attack"),
        Stance.CROUCH: move_id("crouch_sweep"),
    },
    InputAction.ATTACK_3: {Stance.GROUND: move_id("uppercut")},
    InputAction.ATTACK_4: {Stance.GROUND: move_id("dash_attack")},
    InputAction.SPECIAL_ATTACK: {Stance.GROUND: move_id("special_attack")},
}


def move_for_button(action: InputAction, stance: Stance) -> MoveId | None:
    """The move ``action`` throws from ``stance``, or ``None`` if it has none.

    ``None`` is a real answer, not a fallback: it means this button has nothing
    in this posture. The caller turns that into a refusal rather than reaching
    for a neighbouring entry, because substituting a different move is how a
    fighter ends up throwing the standing swing from a crouch.
    """
    return BUTTON_MOVES.get(action, {}).get(stance)
