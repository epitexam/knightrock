"""Ring buffer behavior of ``RollbackSystem`` (Phase 3 #3).

These tests use a fake ``Level`` — a ``SimpleNamespace`` carrying only the
fields ``save_state``/``load_state``/``tick`` need — so the buffer semantics
can be exercised in isolation from the real Level construction.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.rollback import LevelSnapshot, RollbackSystem


def _fake_level(tick: int = 0) -> SimpleNamespace:
    captured: dict[str, SimpleNamespace] = {"snapshot": None}

    def save_state() -> LevelSnapshot:
        snap = LevelSnapshot(tick=level.tick, hit_stop_timer=0.0, respawn_timer=0.0,
                             deaths=0, exit_reached=False,
                             player_dead_emitted=False, completed_emitted=False)
        captured["snapshot"] = snap
        return snap

    def load_state(snapshot: LevelSnapshot) -> None:
        level.tick = snapshot.tick

    level = SimpleNamespace(tick=tick, save_state=save_state, load_state=load_state)
    return level


def test_default_capacity_matches_max_prediction_frames() -> None:
    from src.core.settings import Simulation

    assert RollbackSystem().capacity == Simulation.MAX_PREDICTION_FRAMES


def test_non_positive_capacity_is_rejected() -> None:
    with pytest.raises(ValueError):
        RollbackSystem(capacity=0)


def test_record_populates_buffer_and_updates_tick_queries() -> None:
    level = _fake_level()
    system = RollbackSystem(capacity=4)

    assert len(system) == 0
    assert system.oldest_tick is None
    assert system.latest_tick is None

    system.record(level)
    assert len(system) == 1
    assert system.oldest_tick == 0
    assert system.latest_tick == 0

    level.tick = 1
    system.record(level)
    assert system.oldest_tick == 0
    assert system.latest_tick == 1


def test_rollback_to_rewinds_tick_and_truncates_future() -> None:
    level = _fake_level()
    system = RollbackSystem(capacity=8)

    for t in range(5):
        level.tick = t
        system.record(level)

    assert system.rollback_to(level, 2) is True
    assert level.tick == 2
    assert system.latest_tick == 2
    assert system.oldest_tick == 0
    assert len(system) == 3  # ticks 0, 1, 2 remain


def test_rollback_to_unknown_tick_is_rejected() -> None:
    level = _fake_level()
    system = RollbackSystem(capacity=4)
    system.record(level)

    assert system.rollback_to(level, 99) is False


def test_can_rollback_to_bounds() -> None:
    level = _fake_level()
    system = RollbackSystem(capacity=4)
    for t in range(4):
        level.tick = t
        system.record(level)

    assert system.can_rollback_to(0) is True
    assert system.can_rollback_to(3) is True
    assert system.can_rollback_to(-1) is False
    assert system.can_rollback_to(4) is False


def test_oldest_snapshot_is_evicted_once_capacity_is_reached() -> None:
    level = _fake_level()
    system = RollbackSystem(capacity=3)
    for t in range(5):
        level.tick = t
        system.record(level)

    assert system.oldest_tick == 2  # ticks 0, 1 evicted
    assert system.latest_tick == 4
    assert system.rollback_to(level, 0) is False
    assert system.rollback_to(level, 2) is True


def test_clear_drops_every_buffered_snapshot() -> None:
    level = _fake_level()
    system = RollbackSystem(capacity=4)
    system.record(level)
    system.record(level)

    system.clear()

    assert len(system) == 0
    assert system.oldest_tick is None
    assert system.latest_tick is None
