"""One canonical state vocabulary, with the legacy enums as checked subsets."""

import pytest

from src.shared.state_names import StateName
from src.simulation.states import state_names
from src.simulation.states.enemy_states import EnemyState
from src.simulation.states.null_state_machine import NullStateMachine
from src.simulation.states.player_states import PlayerState


def test_both_fighter_enums_are_generated_from_the_canonical_vocabulary() -> None:
    canonical = {name.value for name in StateName}

    for enum in (PlayerState, EnemyState):
        assert {state.value for state in enum} <= canonical
        for state in enum:
            assert StateName[state.name].value == state.value


def test_the_legacy_constants_keep_their_string_values() -> None:
    assert state_names.KNOCKBACK == "knockback"
    assert state_names.DIZZY == "dizzy"
    assert state_names.DOOMED == "doomed"


def test_null_state_machine_rejects_a_name_outside_the_vocabulary() -> None:
    machine = NullStateMachine()

    with pytest.raises(ValueError, match="not a valid StateName"):
        machine.set_initial_state("not_a_state")

    with pytest.raises(ValueError, match="not a valid StateName"):
        machine.change_state("not_a_state")
