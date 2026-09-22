"""Tests for player state helpers and state functions (states/player_states)."""

from types import SimpleNamespace

import pygame
import pytest

from src.core.settings import Locomotion, Physics
from src.states.player_states import (
    ATTACK_FORBIDDEN_STATES,
    PlayerState,
    _can_attack_interrupt,
    _can_dash,
    _can_guard,
    configure_player_state_machine,
    dash_cancel_open,
    player_ground_return,
    resolve_locomotion_state,
)
from src.states.state_machine import StateMachine


def _mock_state():
    return SimpleNamespace(enter=lambda *a, **kw: None, tags=[])


def _make_entity(**overrides) -> SimpleNamespace:
    defaults = {
        "on_surface": {"floor": True, "left": False, "right": False},
        "velocity": pygame.Vector2(0, 0),
        "speed": Physics.PLAYER_SPEED,
        "move_axis": 0.0,
        "left_held": False,
        "right_held": False,
        "dash": _dash_stub(),
        "guard": SimpleNamespace(can_use=lambda: True),
        "guard_held": False,
        "combat": SimpleNamespace(is_attacking=False),
        "state_machine": SimpleNamespace(current_state_name=None),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- resolve_locomotion_state ---


def _locomotion_entity(ratio: float, current: str | None = None) -> SimpleNamespace:
    speed = Physics.PLAYER_SPEED
    return SimpleNamespace(
        velocity=pygame.Vector2(ratio * speed, 0),
        speed=speed,
        state_machine=SimpleNamespace(current_state_name=current),
    )


def test_resolve_locomotion_classifies_by_ratio_from_idle() -> None:
    assert resolve_locomotion_state(_locomotion_entity(0.0)) == "walk_slow"
    assert resolve_locomotion_state(_locomotion_entity(0.5)) == "walk"
    assert resolve_locomotion_state(_locomotion_entity(0.8)) == "run"
    assert resolve_locomotion_state(_locomotion_entity(1.0)) == "run"


def test_resolve_locomotion_hysteresis_walk_to_run() -> None:
    assert resolve_locomotion_state(_locomotion_entity(0.7, "walk")) == "walk"
    assert resolve_locomotion_state(_locomotion_entity(0.8, "walk")) == "run"


def test_resolve_locomotion_hysteresis_run_to_walk() -> None:
    assert resolve_locomotion_state(_locomotion_entity(0.7, "run")) == "run"
    assert resolve_locomotion_state(_locomotion_entity(0.64, "run")) == "walk"


def test_resolve_locomotion_hysteresis_walk_to_walk_slow() -> None:
    assert resolve_locomotion_state(_locomotion_entity(0.4, "walk")) == "walk"
    assert resolve_locomotion_state(_locomotion_entity(
        Locomotion.WALK_SLOW_DEMOTE - 0.01, "walk"
    )) == "walk_slow"


def test_resolve_locomotion_hysteresis_walk_slow_to_walk() -> None:
    assert resolve_locomotion_state(
        _locomotion_entity(Locomotion.WALK_SLOW_PROMOTE, "walk_slow")
    ) == "walk"
    assert resolve_locomotion_state(_locomotion_entity(0.49, "walk_slow")) == "walk_slow"


def test_resolve_locomotion_walk_slow_from_idle_without_speed_attr() -> None:
    entity = SimpleNamespace(
        velocity=pygame.Vector2(0, 0),
        state_machine=SimpleNamespace(current_state_name=None),
    )
    assert resolve_locomotion_state(entity) == "walk_slow"


# --- player_ground_return ---


def test_player_ground_return_locomotion_when_moving_on_floor() -> None:
    entity = _make_entity(
        left_held=False,
        right_held=True,
        velocity=pygame.Vector2(Physics.PLAYER_SPEED, 0),
    )
    assert player_ground_return(entity) == "run"


def test_player_ground_return_walk_slow_when_barely_moving_on_floor() -> None:
    entity = _make_entity(left_held=True, right_held=False)
    assert player_ground_return(entity) == "walk_slow"


def test_player_ground_return_idle_when_still_on_floor() -> None:
    entity = _make_entity(left_held=False, right_held=False)
    assert player_ground_return(entity) == "idle"


def test_player_ground_return_fall_when_not_on_floor() -> None:
    entity = _make_entity(
        on_surface={"floor": False, "left": False, "right": False},
        right_held=True,
    )
    assert player_ground_return(entity) == "fall"


# --- _can_dash ---


def test_can_dash_true_when_idle() -> None:
    entity = _make_entity()
    sm = StateMachine(entity)
    sm.add_state("idle", _mock_state())
    sm.set_initial_state("idle")
    entity.state_machine = sm
    assert _can_dash(entity) is True


def test_can_dash_false_in_dash_state() -> None:
    entity = _make_entity(
        state_machine=SimpleNamespace(current_state_name=PlayerState.DASH),
    )
    assert _can_dash(entity) is False


def test_can_dash_false_in_hurt_state() -> None:
    entity = _make_entity(
        state_machine=SimpleNamespace(current_state_name=PlayerState.HURT),
    )
    assert _can_dash(entity) is False


def test_can_dash_false_when_no_charges() -> None:
    entity = _make_entity(
        dash=SimpleNamespace(can_use=lambda: False, cancel_request=lambda: None),
    )
    sm = StateMachine(entity)
    sm.add_state("idle", _mock_state())
    sm.set_initial_state("idle")
    entity.state_machine = sm
    assert _can_dash(entity) is False


# --- _can_guard ---


def test_can_guard_true_when_held() -> None:
    entity = _make_entity(
        guard_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.IDLE),
    )
    assert _can_guard(entity) is True


def test_can_guard_true_when_airborne() -> None:
    entity = _make_entity(
        guard_held=True,
        on_surface={"floor": False, "left": False, "right": False},
        state_machine=SimpleNamespace(current_state_name=PlayerState.FALL),
    )
    assert _can_guard(entity) is True


def test_can_guard_false_when_not_held() -> None:
    entity = _make_entity(
        guard_held=False,
        state_machine=SimpleNamespace(current_state_name=PlayerState.IDLE),
    )
    assert _can_guard(entity) is False


def test_can_guard_false_in_hurt_state() -> None:
    entity = _make_entity(
        guard_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.HURT),
    )
    assert _can_guard(entity) is False


def test_can_guard_false_in_attack_state() -> None:
    entity = _make_entity(
        guard_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.ATTACK),
    )
    assert _can_guard(entity) is False


# --- _can_attack_interrupt ---


def test_can_attack_interrupt_true_when_attacking() -> None:
    combat = SimpleNamespace(is_attacking=True, state=SimpleNamespace())
    entity = _make_entity(combat=combat)
    entity.can_attack = lambda: True
    assert _can_attack_interrupt(entity) is True


def test_can_attack_interrupt_false_when_not_attacking() -> None:
    combat = SimpleNamespace(is_attacking=False, state=SimpleNamespace())
    entity = _make_entity(combat=combat)
    entity.can_attack = lambda: True
    assert _can_attack_interrupt(entity) is False


# --- ATTACK_FORBIDDEN_STATES ---


def test_attack_forbidden_states_contains_expected_members() -> None:
    assert PlayerState.WALL_SLIDE in ATTACK_FORBIDDEN_STATES
    assert PlayerState.GUARD in ATTACK_FORBIDDEN_STATES
    assert PlayerState.CROUCH in ATTACK_FORBIDDEN_STATES
    assert PlayerState.HURT in ATTACK_FORBIDDEN_STATES
    assert PlayerState.DASH in ATTACK_FORBIDDEN_STATES
    assert PlayerState.STAGGER in ATTACK_FORBIDDEN_STATES
    assert PlayerState.KNOCKBACK in ATTACK_FORBIDDEN_STATES
    assert PlayerState.IDLE not in ATTACK_FORBIDDEN_STATES
    assert PlayerState.WALK_SLOW not in ATTACK_FORBIDDEN_STATES
    assert PlayerState.WALK not in ATTACK_FORBIDDEN_STATES
    assert PlayerState.RUN not in ATTACK_FORBIDDEN_STATES


# --- configure_player_state_machine ---


def _dash_stub(duration: float = 0.08, duration_timer: float = 0.0):
    """Dash double with the timers the cancel-window helper reads."""
    return SimpleNamespace(
        can_use=lambda: True,
        cancel_request=lambda: None,
        in_coyote=lambda: False,
        duration=duration,
        duration_timer=duration_timer,
    )


def _guard_stub():
    return SimpleNamespace(can_use=lambda: True)


def test_configure_state_machine_sets_all_states() -> None:
    entity = _make_entity(dash=_dash_stub(), guard=_guard_stub())
    configure_player_state_machine(entity)
    sm = entity.state_machine
    assert sm.current_state_name == "idle"
    assert len(list(PlayerState)) == 16
    for state_name in PlayerState:
        assert state_name.value in sm.states


def test_configure_state_machine_registers_interrupts() -> None:
    entity = _make_entity(dash=_dash_stub(), guard=_guard_stub())
    configure_player_state_machine(entity)
    sm = entity.state_machine
    assert len(sm._interrupts) == 4
    targets = {t for _, t, _ in sm._interrupts}
    assert PlayerState.DASH.value in targets
    assert PlayerState.GUARD.value in targets
    assert PlayerState.ATTACK.value in targets
    assert PlayerState.CROUCH.value in targets


# --- Dash cancel window ---


def test_dash_cancel_open_is_immediate_with_the_shipped_window() -> None:
    """The shipped window is 0.0: a dash is cancellable as soon as it starts."""
    assert Physics.DASH_CANCEL_WINDOW == 0.0
    entity = _make_entity(dash=_dash_stub(duration=0.08, duration_timer=0.063))
    assert dash_cancel_open(entity) is True


def test_dash_cancel_open_honours_a_committed_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    """A positive window keeps the dash committed until enough time elapsed."""
    monkeypatch.setattr(Physics, "DASH_CANCEL_WINDOW", 0.03)
    fresh = _make_entity(dash=_dash_stub(duration=0.08, duration_timer=0.08))
    elapsed = _make_entity(dash=_dash_stub(duration=0.08, duration_timer=0.04))
    assert dash_cancel_open(fresh) is False
    assert dash_cancel_open(elapsed) is True


def test_can_attack_interrupt_true_during_dash_after_cancel_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attack allowed from dash once the cancel window has elapsed."""
    monkeypatch.setattr(Physics, "DASH_CANCEL_WINDOW", 0.03)
    entity = _make_entity(
        combat=SimpleNamespace(is_attacking=True, state=SimpleNamespace()),
        state_machine=SimpleNamespace(current_state_name=PlayerState.DASH),
        dash=_dash_stub(duration=0.08, duration_timer=0.04),  # 0.04s elapsed
    )
    assert _can_attack_interrupt(entity) is True


def test_can_attack_interrupt_false_during_dash_before_cancel_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attack blocked from a dash still inside its cancel window."""
    monkeypatch.setattr(Physics, "DASH_CANCEL_WINDOW", 0.03)
    entity = _make_entity(
        combat=SimpleNamespace(is_attacking=True, state=SimpleNamespace()),
        state_machine=SimpleNamespace(current_state_name=PlayerState.DASH),
        dash=_dash_stub(duration=0.08, duration_timer=0.08),  # 0.0s elapsed
    )
    assert _can_attack_interrupt(entity) is False


def test_can_guard_true_during_dash_after_cancel_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard allowed from dash once the cancel window has elapsed."""
    monkeypatch.setattr(Physics, "DASH_CANCEL_WINDOW", 0.03)
    entity = _make_entity(
        guard_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.DASH),
        dash=_dash_stub(duration=0.08, duration_timer=0.04),  # 0.04s elapsed
    )
    assert _can_guard(entity) is True


def test_can_guard_false_during_dash_before_cancel_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard blocked from a dash still inside its cancel window."""
    monkeypatch.setattr(Physics, "DASH_CANCEL_WINDOW", 0.03)
    entity = _make_entity(
        guard_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.DASH),
        dash=_dash_stub(duration=0.08, duration_timer=0.08),  # 0.0s elapsed
    )
    assert _can_guard(entity) is False


# --- Dash coyote ---


def test_can_attack_interrupt_true_during_dash_coyote() -> None:
    """Attack allowed during dash coyote window after dash ends."""
    entity = _make_entity(
        combat=SimpleNamespace(is_attacking=True, state=SimpleNamespace()),
        state_machine=SimpleNamespace(current_state_name=PlayerState.IDLE),
        dash=SimpleNamespace(in_coyote=lambda: True),
    )
    assert _can_attack_interrupt(entity) is True


def test_can_guard_true_during_dash_coyote() -> None:
    """Guard allowed during dash coyote window after dash ends."""
    entity = _make_entity(
        guard_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.IDLE),
        dash=SimpleNamespace(in_coyote=lambda: True),
    )
    assert _can_guard(entity) is True
