"""A prompt takes its directions from the directional keys, not from Jump."""

from src.core.input.input_actions import InputAction
from src.entities.player_input import PlayerInputHandler
from src.entities.player_kit import Direction


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
