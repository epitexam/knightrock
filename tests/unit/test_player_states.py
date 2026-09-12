"""Tests for player state helpers and state functions (states/player_states)."""

from types import SimpleNamespace

import pygame

from src.states.player_states import (
    ATTACK_FORBIDDEN_STATES,
    PlayerState,
    _can_attack_interrupt,
    _can_block,
    _can_dash,
    configure_player_state_machine,
    player_ground_return,
)
from src.states.state_machine import StateMachine


def _mock_state():
    return SimpleNamespace(enter=lambda *a, **kw: None, tags=[])


def _make_entity(**overrides) -> SimpleNamespace:
    defaults = dict(
        on_surface={"floor": True, "left": False, "right": False},
        velocity=pygame.Vector2(0, 0),
        move_axis=0.0,
        left_held=False,
        right_held=False,
        dash=SimpleNamespace(can_use=lambda: True, cancel_request=lambda: None),
        block=SimpleNamespace(can_use=lambda: True, apply_exit_cooldown=lambda: None),
        block_stamina=0.5,
        max_block_stamina=0.75,
        block_held=False,
        combat=SimpleNamespace(is_attacking=False),
        state_machine=SimpleNamespace(current_state_name=None),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- player_ground_return ---


def test_player_ground_return_run_when_moving_on_floor() -> None:
    entity = _make_entity(left_held=False, right_held=True)
    assert player_ground_return(entity) == "run"


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


# --- _can_block ---


def test_can_block_true_when_grounded() -> None:
    entity = _make_entity(
        block_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.IDLE),
    )
    assert _can_block(entity) is True


def test_can_block_false_when_airborne() -> None:
    entity = _make_entity(
        block_held=True,
        on_surface={"floor": False, "left": False, "right": False},
        state_machine=SimpleNamespace(current_state_name=PlayerState.IDLE),
    )
    assert _can_block(entity) is False


def test_can_block_false_when_not_held() -> None:
    entity = _make_entity(
        block_held=False,
        state_machine=SimpleNamespace(current_state_name=PlayerState.IDLE),
    )
    assert _can_block(entity) is False


def test_can_block_false_in_hurt_state() -> None:
    entity = _make_entity(
        block_held=True,
        state_machine=SimpleNamespace(current_state_name=PlayerState.HURT),
    )
    assert _can_block(entity) is False


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
    assert PlayerState.BLOCK in ATTACK_FORBIDDEN_STATES
    assert PlayerState.HURT in ATTACK_FORBIDDEN_STATES
    assert PlayerState.DASH in ATTACK_FORBIDDEN_STATES
    assert PlayerState.STAGGER in ATTACK_FORBIDDEN_STATES
    assert PlayerState.KNOCKBACK in ATTACK_FORBIDDEN_STATES
    assert PlayerState.IDLE not in ATTACK_FORBIDDEN_STATES
    assert PlayerState.RUN not in ATTACK_FORBIDDEN_STATES


# --- configure_player_state_machine ---


def _dash_stub():
    return SimpleNamespace(can_use=lambda: True, cancel_request=lambda: None)


def _block_stub():
    return SimpleNamespace(
        can_use=lambda: True,
        apply_exit_cooldown=lambda: None,
    )


def test_configure_state_machine_sets_all_states() -> None:
    entity = _make_entity(dash=_dash_stub(), block=_block_stub())
    configure_player_state_machine(entity)
    sm = entity.state_machine
    assert sm.current_state_name == "idle"
    for state_name in PlayerState:
        assert state_name.value in sm.states


def test_configure_state_machine_registers_interrupts() -> None:
    entity = _make_entity(dash=_dash_stub(), block=_block_stub())
    configure_player_state_machine(entity)
    sm = entity.state_machine
    assert len(sm._interrupts) == 3
    targets = {t for _, t, _ in sm._interrupts}
    assert PlayerState.DASH.value in targets
    assert PlayerState.BLOCK.value in targets
    assert PlayerState.ATTACK.value in targets
