"""A prompt takes its directions from the directional keys, not from Jump."""

from dataclasses import replace

import pygame
import pytest

from src.platform.input.input_bindings import InputBindings
from src.platform.input.input_manager import InputManager
from src.platform.input.input_provider import LocalInputProvider
from src.shared.input_actions import InputAction
from src.simulation.entities.player_input import PlayerInputHandler
from src.simulation.entities.player_kit import Direction
from tests.headless.test_input_provider import FakeJoystick


class _Input:
    def __init__(self, pressed: frozenset[InputAction]) -> None:
        self.pressed = pressed

    def axis(self, _action: InputAction) -> float:
        return 0.0

    def held(self, action: InputAction) -> bool:
        return action in self.pressed

    def just_pressed(self, action: InputAction) -> bool:
        return action in self.pressed


def _handler(pressed: frozenset[InputAction]) -> PlayerInputHandler:
    player = type("Stub", (), {"input_manager": _Input(pressed)})()
    return PlayerInputHandler(player)  # type: ignore[arg-type]


def test_the_up_arrow_is_up() -> None:
    assert _handler(frozenset({InputAction.MOVE_UP}))._directions() == [Direction.UP]


def test_jump_is_not_a_prompt_direction() -> None:
    assert _handler(frozenset({InputAction.JUMP}))._directions() == []


def test_down_and_the_horizontal_axis_are_unchanged() -> None:
    assert _handler(frozenset({InputAction.MOVE_DOWN}))._directions() == [Direction.DOWN]


def test_a_latched_pad_button_reaches_the_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stub above cannot see provider bugs, so drive one real tap through."""
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: {})
    bindings = InputBindings()
    gameplay = replace(
        bindings.gameplay,
        gamepad_buttons={InputAction.MOVE_UP: 7},
        gamepad_axes={},
        gamepad_hats={},
    )
    provider = LocalInputProvider(replace(bindings, gameplay=gameplay))
    joystick = FakeJoystick()
    provider.connect_joystick(joystick)  # type: ignore[arg-type]
    manager = InputManager(provider)
    manager.update()
    provider.note_event(
        pygame.event.Event(pygame.JOYBUTTONDOWN, button=7, instance_id=joystick.get_instance_id())
    )
    manager.update()

    player = type("Stub", (), {"input_manager": manager})()
    assert PlayerInputHandler(player)._directions() == [Direction.UP]
