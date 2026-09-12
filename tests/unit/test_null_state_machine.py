"""Tests for the NullStateMachine (states/null_state_machine)."""

from types import SimpleNamespace

from src.states.null_state_machine import NullStateMachine


def test_set_initial_state_stores_name() -> None:
    sm = NullStateMachine()
    assert sm.current_state_name is None
    sm.set_initial_state("idle")
    assert sm.current_state_name == "idle"


def test_update_is_a_noop() -> None:
    sm = NullStateMachine()
    sm.update(1 / 60)  # must not raise
    assert sm.current_state_name is None


def test_change_state_is_a_noop() -> None:
    sm = NullStateMachine()
    sm.change_state("run", force=True)  # must not raise
    sm.change_state("run")  # must not raise


def test_add_state_is_a_noop() -> None:
    sm = NullStateMachine()
    sm.add_state("idle", SimpleNamespace())  # must not raise


def test_add_interrupt_is_a_noop() -> None:
    sm = NullStateMachine()
    sm.add_interrupt("attack", lambda: True, priority=10)  # must not raise


def test_buffer_input_is_a_noop() -> None:
    sm = NullStateMachine()
    sm.buffer_input("attack", window=0.2)  # must not raise


def test_consume_input_returns_false() -> None:
    sm = NullStateMachine()
    assert sm.consume_input("attack") is False


def test_interface_matches_state_machine() -> None:
    """NullStateMachine must expose the same surface as StateMachine."""
    sm = NullStateMachine()
    sm.set_initial_state("idle")
    assert sm.current_state_name == "idle"
    assert sm.consume_input("anything") is False
    # Re-setting is fine too
    sm.set_initial_state("run")
    assert sm.current_state_name == "run"