from dataclasses import dataclass

from src.core.input.input_actions import InputAction


@dataclass(frozen=True)
class InputState:
    move_axis: float = 0.0
    held_actions: frozenset[InputAction] = frozenset()

    def __post_init__(self) -> None:
        if not -1.0 <= self.move_axis <= 1.0:
            raise ValueError("move_axis must be between -1.0 and 1.0")
        if not isinstance(self.held_actions, frozenset):
            raise TypeError("held_actions must be a frozenset")
        if any(
            not isinstance(action, InputAction) or action.value.startswith("ui_")
            for action in self.held_actions
        ):
            raise ValueError("InputState only accepts gameplay actions")
