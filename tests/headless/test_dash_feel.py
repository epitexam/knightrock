"""The dash, played: one length whatever the stick, no stop on the way into a run.

A dash is a burst that eases out (``Physics.DASH_CURVE``): it goes about as far
whether the stick is held or not, hands its speed to the run when the stick
holds its way, turns round on an early push back, and three in a row lock it
for ``Physics.DASH_PENALTY_TIME`` -- a breath, not a punishment.
"""

from __future__ import annotations

import pytest

from src.core.settings import Physics
from tests.headless.arena import DASH, DT, arena, settle


def _dash(axis: float, ticks: int = 20, dt: float = DT) -> tuple[float, list[float], str]:
    level, pad, player = arena()
    settle(level)
    start = player.hitbox.centerx
    pad.axis = axis
    pad.held = frozenset({DASH})
    level.update(dt)
    pad.held = frozenset()
    speeds = []
    for _ in range(round(ticks * DT / dt)):
        level.update(dt)
        speeds.append(player.velocity.x)
    return player.hitbox.centerx - start, speeds, str(player.state_machine.current_state_name)


def test_a_dash_goes_about_as_far_whether_the_stick_is_held_or_not() -> None:
    idle, _, _ = _dash(0.0, ticks=12)
    held, _, _ = _dash(1.0, ticks=12)

    assert 70.0 <= idle <= 120.0
    held_dash_only = held - Physics.PLAYER_SPEED * (12 * DT - Physics.DASH_DURATION)
    assert held_dash_only == pytest.approx(idle, rel=0.35)


def test_a_dash_into_a_run_never_stops() -> None:
    _, speeds, state = _dash(1.0)

    assert min(speeds) >= Physics.PLAYER_SPEED * 0.95, "no dip to zero between dash and run"
    assert speeds == sorted(speeds, reverse=True), "it eases out, it does not lurch"
    assert "run" in state


def test_a_dash_let_go_glides_and_stops() -> None:
    _, speeds, _ = _dash(0.0)

    assert speeds[0] > speeds[5] > 0.0
    assert speeds[-1] == 0.0


def test_an_early_push_back_turns_the_dash_round() -> None:
    level, pad, player = arena()
    settle(level)
    start = player.hitbox.centerx
    pad.axis = 1.0
    pad.held = frozenset({DASH})
    level.update(DT)
    pad.held = frozenset()
    pad.axis = -1.0
    for _ in range(10):
        level.update(DT)

    assert player.hitbox.centerx < start
    assert not player.facing_right


def test_the_last_charge_locks_the_dash_for_a_breath_only() -> None:
    level, pad, player = arena()
    settle(level)
    player.dash.charges = 1
    player.dash.recharge_timer = 10.0  # no charge back during the test
    pad.held = frozenset({DASH})
    level.update(DT)
    pad.held = frozenset()

    assert player.dash.charges == 0
    assert 0.0 < player.dash.penalty_timer <= Physics.DASH_PENALTY_TIME <= 1.0


def test_the_dash_is_the_same_length_at_any_tick_rate() -> None:
    at_60, _, _ = _dash(0.0, ticks=14, dt=1 / 60)
    at_120, _, _ = _dash(0.0, ticks=14, dt=1 / 120)

    assert at_120 == pytest.approx(at_60, rel=0.1)
