"""Tests d'orchestration de l'InputManager avec un provider scripté (Phase 1 #10)."""

from src.core.input.input_manager import InputManager
from src.core.input.input_state import InputState


class ScriptedProvider:
    """Provider renvoyant une séquence d'InputState, puis un état neutre."""

    def __init__(self, states: list[InputState]) -> None:
        self._states = states
        self.poll_count = 0

    def poll(self) -> InputState:
        if self._states:
            self.poll_count += 1
            return self._states.pop(0)
        return InputState()


def test_input_manager_detects_just_pressed_edges() -> None:
    provider = ScriptedProvider([InputState(), InputState(jump_held=True)])
    manager = InputManager(provider)  # type: ignore[arg-type]

    manager.update()
    assert manager.jump_just_pressed is False

    manager.update()
    assert manager.jump_just_pressed is True

    manager.update()
    # Le bouton est toujours maintenu : plus de front montant.
    assert manager.jump_just_pressed is False


def test_input_manager_applies_move_axis_deadzone() -> None:
    provider = ScriptedProvider([InputState(move_axis=0.05)])
    manager = InputManager(provider)  # type: ignore[arg-type]

    manager.update()

    assert manager.left_held is False
    assert manager.right_held is False
    assert manager.move_axis == 0.05


def test_input_manager_resolves_direction_from_axis() -> None:
    provider = ScriptedProvider([InputState(move_axis=-0.8)])
    manager = InputManager(provider)  # type: ignore[arg-type]

    manager.update()

    assert manager.left_held is True
    assert manager.right_held is False


def test_input_manager_apply_remote_state_bypasses_provider() -> None:
    manager = InputManager()  # nul provider
    remote = InputState(move_axis=0.7, attack1_held=True)

    manager.apply_remote_state(remote)

    assert manager.move_axis == 0.7
    assert manager.attack1_held is True
    # Transition depuis l'état vide initial : front montant détecté.
    assert manager.attack1_just_pressed is True

    manager.apply_remote_state(remote)
    # État identique à l'état précédent : plus de front montant.
    assert manager.attack1_just_pressed is False


def test_input_manager_attack_edges_are_independent() -> None:
    provider = ScriptedProvider(
        [
            InputState(attack1_held=True, attack2_held=True),
            InputState(attack1_held=False, attack2_held=True),
        ]
    )
    manager = InputManager(provider)  # type: ignore[arg-type]

    manager.update()
    assert manager.attack1_just_pressed is True
    assert manager.attack2_just_pressed is True

    manager.update()
    assert manager.attack1_just_released is True
    assert manager.attack2_just_pressed is False
