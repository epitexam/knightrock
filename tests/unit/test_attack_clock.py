"""The attack clock's speed: a fast clock shortens the startup and the recovery only."""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.combat.attack_state import AttackStateMachine
from src.combat.frame_data import PhaseState, move_id
from tests.unit.helpers import make_attack, make_phase

DT = 1 / 60
MOVE = move_id("test")


def _machine(startup: int, active: int, recovery: int, speed: float = 1.0) -> AttackStateMachine:
    machine = AttackStateMachine(
        {MOVE: make_attack(make_phase(startup=startup, active=active, recovery=recovery))}
    )
    machine.speed = speed
    assert machine.start(MOVE)
    return machine


def _play(machine: AttackStateMachine) -> list[PhaseState]:
    """The sub-state seen by the collision pass on each tick, until the attack ends."""
    seen: list[PhaseState] = []
    for _ in range(600):
        machine.update(DT)
        if machine.is_idle:
            return seen
        seen.append(machine.sub_state)
    raise AssertionError("the attack never ended")


def test_auto_into_continues_in_place_and_keeps_the_charge() -> None:
    """The follow-through is one gesture: no cooldown, no new combo entry."""
    follow = move_id("follow")
    first = replace(make_phase(startup=1, active=1, recovery=1), auto_into=follow)
    machine = AttackStateMachine(
        {MOVE: make_attack(first), follow: make_attack(make_phase(startup=0, active=1, recovery=1))}
    )
    assert machine.start(MOVE, charge_multiplier=1.7)

    for _ in range(12):
        machine.update(DT)
        if machine.attack_name == follow:
            break

    assert machine.attack_name == follow
    assert machine.charge_multiplier == 1.7
    assert machine.phase_index == 0
    assert machine.save_state().charge_multiplier == 1.7


def test_at_speed_one_an_attack_lasts_its_frame_data() -> None:
    seen = _play(_machine(6, 4, 10))

    # Twenty frames are twenty updates; the last one ends the attack, and the
    # sixth is already the first active frame.
    assert len(seen) == 6 + 4 + 10 - 1
    assert seen.count(PhaseState.STARTUP) == 5
    assert seen.count(PhaseState.ACTIVE) == 4
    assert seen.count(PhaseState.RECOVERY) == 10


@pytest.mark.parametrize("speed", [1.15, 1.3, 1.45, 1.5, 2.0])
def test_a_fast_clock_never_shortens_the_active_window(speed: float) -> None:
    normal = _play(_machine(6, 4, 10))
    fast = _play(_machine(6, 4, 10, speed))

    assert fast.count(PhaseState.ACTIVE) == normal.count(PhaseState.ACTIVE)
    assert len(fast) < len(normal)


def test_a_fast_clock_shortens_the_startup_and_the_recovery() -> None:
    normal = _play(_machine(12, 4, 12))
    fast = _play(_machine(12, 4, 12, 1.5))

    assert fast.count(PhaseState.STARTUP) < normal.count(PhaseState.STARTUP)
    assert fast.count(PhaseState.RECOVERY) < normal.count(PhaseState.RECOVERY)
    # 24 frames of startup and recovery at 1.5 is 16 ticks, plus the 4 active.
    assert len(fast) + 1 == pytest.approx(16 + 4, abs=1)


def test_a_slowed_clock_stretches_the_attack() -> None:
    """What a rush does to an enemy: its delta is a quarter, so is its attack."""
    machine = _machine(4, 2, 4)
    ticks = 0
    while not machine.is_idle:
        machine.update(DT * 0.25)
        ticks += 1
        assert ticks < 600

    assert ticks == pytest.approx(10 * 4, abs=1)


def test_the_speed_is_not_part_of_a_snapshot() -> None:
    """It is derived by the owner before every update, so a restore leaves it alone."""
    machine = _machine(6, 4, 10, 1.5)
    snapshot = machine.save_state()

    machine.speed = 1.0
    machine.load_state(snapshot)

    assert machine.speed == 1.0
    assert not hasattr(snapshot, "speed")
