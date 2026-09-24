from dataclasses import dataclass

from src.core.input.input_actions import InputAction


@dataclass(frozen=True)
class InputState:
    move_axis: float = 0.0
    held_actions: frozenset[InputAction] = frozenset()
