"""What an attack does with the time it is handed late.

The state advances at most one frame per tick, on purpose: an active window has
to receive a collision pass, and two frames in one tick would skip one. What
happens to the *rest* of a late tick is the deliberate half of that design,
and it was only ever written in a comment -- so it is asserted here, where a
future change to the accumulator has to argue with a test.
"""

import pytest

from src.combat.attack_state import AttackStateMachine
from tests.unit.helpers import make_attack as attack
from tests.unit.helpers import make_phase as phase

_FRAME = AttackStateMachine._FRAME_DURATION


def _state() -> AttackStateMachine:
    definition = attack(phase(startup=10, active=2, recovery=10))
    state = AttackStateMachine({"test": definition})
    state.start("test")
    return state


def test_one_tick_advances_one_frame() -> None:
    state = _state()
    assert state.frame_counter == 0, "start() sets up the attack, it does not play it"
    state.update(_FRAME)
    assert state.frame_counter == 1


def test_a_late_tick_resolves_one_frame_and_keeps_the_surplus() -> None:
    """No time is lost: a caller three frames late plays one and banks two.

    The alternative -- dropping the surplus -- would play the same number of
    frames over a shorter attack and lose its tail. Each ``update`` resolves at
    most one frame from the bank, which is what keeps an active window one
    collision pass wide.
    """
    state = _state()
    state.update(_FRAME * 3)

    assert state.frame_counter == 1
    assert state._accumulator == pytest.approx(_FRAME * 2)

    # Half a frame later: the bank already has two to spend, so one more is
    # resolved immediately rather than waiting a whole frame for it.
    state.update(_FRAME * 0.5)
    assert state.frame_counter == 2
    assert state._accumulator == pytest.approx(_FRAME * 1.5)


def test_a_hitch_stretches_the_attack_in_time_not_in_frames() -> None:
    """What a hitch costs is elapsed time, never frames of the attack.

    Counted as frames consumed until the machine goes idle: the number of
    *updates* differs by design -- banking is the whole point -- and what must
    not differ is how much of the attack plays.
    """

    def run(pacing: float) -> tuple[int, int]:
        state = _state()
        frames = 0
        updates = 0
        while not state.is_idle:
            before = state.frame_counter
            state.update(pacing)
            updates += 1
            if not state.is_idle:
                frames += state.frame_counter - before
        return frames, updates

    smooth_frames, smooth_updates = run(_FRAME)
    hitched_frames, hitched_updates = run(_FRAME * 4)

    assert smooth_frames == hitched_frames, "the hitch consumed different attack frames"
    assert hitched_updates * (_FRAME * 4) > smooth_updates * _FRAME, (
        "the attack did not take longer to play out"
    )


def test_an_idle_state_takes_no_time() -> None:
    state = _state()
    state.update(_FRAME)
    assert state._accumulator == pytest.approx(0.0)
