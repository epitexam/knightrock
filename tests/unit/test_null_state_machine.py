"""Tests for the NullStateMachine (states/null_state_machine)."""

import inspect
from types import SimpleNamespace

from src.states.null_state_machine import NullStateMachine
from src.states.state_machine import StateMachine


def _public_methods(cls: type) -> dict[str, list[str]]:
    return {
        name: list(inspect.signature(member).parameters)
        for name, member in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_")
    }


def test_interface_matches_state_machine() -> None:
    """Callers hold either machine, so every public method has to exist on both.

    Compared method by method, parameter names included: a caller passing
    ``force=`` to the real machine has to be able to pass it to this one.
    """
    real = _public_methods(StateMachine)
    null = _public_methods(NullStateMachine)

    assert real == null


def test_set_initial_state_stores_name() -> None:
    sm = NullStateMachine()
    assert sm.current_state_name is None
    sm.set_initial_state("idle")
    assert sm.current_state_name == "idle"


def test_registration_and_transitions_leave_it_stateless() -> None:
    """Every mutator is accepted and changes nothing a caller can read."""
    sm = NullStateMachine()

    sm.add_state("idle", SimpleNamespace())
    sm.add_interrupt("attack", lambda: True, priority=10)
    sm.buffer_input("attack", window=0.2)
    sm.change_state("run", force=True)
    sm.update(1 / 60)

    assert sm.current_state_name is None
    assert sm.consume_input("attack") is False
    assert sm.has_tag("anything") is False
