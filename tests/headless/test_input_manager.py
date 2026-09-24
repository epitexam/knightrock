import pytest

from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_state import InputState
from tests.unit.helpers import ScriptedInputProvider


def test_input_manager_detects_action_edges() -> None:
    provider = ScriptedInputProvider(
        [InputState(), InputState(held_actions=frozenset({InputAction.JUMP}))]
    )
    manager = InputManager(provider)  # type: ignore[arg-type]

    manager.update()
    assert manager.just_pressed(InputAction.JUMP) is False

    manager.update()
    assert manager.held(InputAction.JUMP) is True
    assert manager.just_pressed(InputAction.JUMP) is True

    manager.update()
    assert manager.just_pressed(InputAction.JUMP) is False
    assert manager.just_released(InputAction.JUMP) is True

    manager.update()
    assert manager.just_released(InputAction.JUMP) is False


def test_input_manager_exposes_move_axis() -> None:
    manager = InputManager(ScriptedInputProvider([InputState(move_axis=-0.8)]))  # type: ignore[arg-type]

    manager.update()

    assert manager.axis(InputAction.MOVE_X) == -0.8
    assert manager.axis(InputAction.MOVE_X) < 0.0


def test_input_manager_rejects_invalid_action_channels() -> None:
    manager = InputManager()

    with pytest.raises(ValueError, match="analog action"):
        manager.axis(InputAction.JUMP)
    with pytest.raises(ValueError, match="axis"):
        manager.held(InputAction.MOVE_X)
    with pytest.raises(ValueError, match="axis"):
        manager.just_pressed(InputAction.MOVE_X)
    with pytest.raises(ValueError, match="axis"):
        manager.just_released(InputAction.MOVE_X)


def test_input_state_rejects_invalid_invariants() -> None:
    with pytest.raises(ValueError, match="move_axis"):
        InputState(move_axis=2.0)
    with pytest.raises(TypeError, match="frozenset"):
        InputState(held_actions={InputAction.JUMP})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="gameplay"):
        InputState(held_actions=frozenset({InputAction.UI_UP}))


def test_input_manager_apply_remote_state_bypasses_provider() -> None:
    manager = InputManager()
    remote = InputState(
        move_axis=0.7,
        held_actions=frozenset({InputAction.ATTACK_1}),
    )

    manager.apply_remote_state(remote)

    assert manager.axis(InputAction.MOVE_X) == 0.7
    assert manager.held(InputAction.ATTACK_1) is True
    assert manager.just_pressed(InputAction.ATTACK_1) is True

    manager.apply_remote_state(remote)
    assert manager.just_pressed(InputAction.ATTACK_1) is False


def test_input_manager_attack_edges_are_independent() -> None:
    provider = ScriptedInputProvider(
        [
            InputState(held_actions=frozenset({InputAction.ATTACK_1, InputAction.ATTACK_2})),
            InputState(held_actions=frozenset({InputAction.ATTACK_2})),
        ]
    )
    manager = InputManager(provider)  # type: ignore[arg-type]

    manager.update()
    assert manager.just_pressed(InputAction.ATTACK_1) is True
    assert manager.just_pressed(InputAction.ATTACK_2) is True

    manager.update()
    assert manager.just_released(InputAction.ATTACK_1) is True
    assert manager.just_pressed(InputAction.ATTACK_2) is False


def test_set_provider_replaces_the_source() -> None:
    manager = InputManager()
    manager.set_provider(
        ScriptedInputProvider([InputState(held_actions=frozenset({InputAction.GUARD}))])  # type: ignore[arg-type]
    )

    manager.update()

    assert manager.held(InputAction.GUARD) is True
