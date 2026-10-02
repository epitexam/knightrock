"""Which button throws what, from which posture -- and what a refusal means.

The move table is the answer to "which attacks are available now", which used to
be one ternary in the input handler plus four hand-kept lists of states that
disagreed with each other. These tests pin the table against the gate and
against the buffer, because the bug this replaces was a *combination*: the table
picking the right move and the gate accepting it were two separate claims, and
only one of them was ever tested.
"""

import pytest

from src.combat.frame_data import Stance
from src.combat.refusal import Refusal
from src.core.input.input_actions import InputAction
from src.entities.attack_moves import BUTTON_MOVES, move_for_button
from src.entities.player_input import ATTACK_BUTTONS

ATTACK_ACTIONS = tuple(BUTTON_MOVES)


def test_every_bound_button_is_in_the_press_order() -> None:
    """A button the table knows but the handler never reads is unreachable.

    The reverse is worse and easier to miss: a button the handler reads that the
    table does not know throws nothing at all, silently, on every press.
    """
    assert set(ATTACK_ACTIONS) == set(ATTACK_BUTTONS)


def test_every_move_in_the_table_exists_and_is_legal_from_where_it_is_bound() -> None:
    """The table may only name a move that permits the posture it is bound to.

    Two errors caught at once: a typo in the name, which would refuse every
    press of that button, and a move bound to a posture its ``stances`` does not
    list, which would refuse just as silently.
    """
    from src.combat.attack_data import PLAYER_ATTACKS

    for action, by_stance in BUTTON_MOVES.items():
        for stance, move in by_stance.items():
            definition = PLAYER_ATTACKS.get(move)
            assert definition is not None, f"{action} names an unregistered move {move}"
            assert stance in definition.stances, (
                f"{action} binds {move} to {stance.value}, which it does not allow"
            )


def test_the_special_does_not_come_out_of_a_crouch() -> None:
    """A 110-frame commitment is not a posture's idea of a poke.

    It is also the move with the highest cost in the table, and letting it out
    of a crouch would invert the whole point of the posture: the fighter went
    down to be hard to hit, then stood still for two seconds on purpose.
    """
    assert Stance.CROUCH not in BUTTON_MOVES[InputAction.SPECIAL_ATTACK]


@pytest.mark.parametrize(
    ("action", "stance"),
    [
        (action, stance)
        for action, by_stance in BUTTON_MOVES.items()
        for stance in (Stance.GROUND, Stance.CROUCH, Stance.AIR)
        if stance not in by_stance
    ],
)
def test_a_button_with_no_move_in_a_posture_has_none(action: InputAction, stance: Stance) -> None:
    """Absent is an answer, and it must not fall back to a neighbour.

    The bug this replaces: a crouched fighter pressed ATTACK_1 and got
    ``light_attack`` -- the standing move, with a hitbox authored for a standing
    collider 40% taller. Substituting "the closest move" is how that happened
    and is exactly what must not happen now.
    """
    assert move_for_button(action, stance) is None


def test_only_cooldown_is_worth_buffering() -> None:
    """``is_retryable`` is the whole reason the refusal is a value.

    A press refused on cooldown is still the press the player made. One refused
    because the fighter is in the wrong posture, or hurt, or because the move is
    unknown, is not: keeping those would fire a move the player stopped asking
    for seconds ago.
    """
    assert Refusal.COOLDOWN.is_retryable
    for refusal in (
        Refusal.NONE,
        Refusal.STANCE,
        Refusal.BUSY,
        Refusal.UNKNOWN,
        Refusal.CHARGING,
        Refusal.NO_CANCEL,
    ):
        assert not refusal.is_retryable, refusal


def test_a_success_reads_as_true_so_the_old_call_sites_still_work() -> None:
    """The enum landed without rewriting forty call sites because of this.

    Every ``assert combat.start_attack(x)`` and ``if not ...`` in the suite kept
    its meaning when the return type changed from ``bool`` to ``Refusal``. Worth
    pinning, since flipping it would make all of them quietly invert.
    """
    assert bool(Refusal.NONE) is True
    assert bool(Refusal.COOLDOWN) is False
    assert bool(Refusal.STANCE) is False
