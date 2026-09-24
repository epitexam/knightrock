from copy import copy

from src.core.input.input_actions import InputAction
from src.core.input.input_provider import InputProvider, NullInputProvider
from src.core.input.input_state import InputState
from src.core.settings import Input as InputSettings


class InputManager:
    def __init__(self, provider: InputProvider | None = None) -> None:
        self._provider: InputProvider = provider or NullInputProvider()
        self._current_state = InputState()
        self._prev_state = InputState()

    def set_provider(self, provider: InputProvider) -> None:
        self._provider = provider

    def apply_remote_state(self, state: InputState) -> None:
        self._prev_state = copy(self._current_state)
        self._current_state = state

    def update(self) -> None:
        self._prev_state = self._current_state
        self._current_state = self._provider.poll()

    def axis(self, action: InputAction) -> float:
        if action is not InputAction.MOVE_X:
            raise ValueError(f"Action {action.value} is not an analog action")
        return self._current_state.move_axis

    def held(self, action: InputAction) -> bool:
        self._require_discrete(action)
        return action in self._current_state.held_actions

    def just_pressed(self, action: InputAction) -> bool:
        self._require_discrete(action)
        return action in self._current_state.held_actions and action not in (
            self._prev_state.held_actions
        )

    def just_released(self, action: InputAction) -> bool:
        self._require_discrete(action)
        return action not in self._current_state.held_actions and action in (
            self._prev_state.held_actions
        )

    @staticmethod
    def _require_discrete(action: InputAction) -> None:
        if action is InputAction.MOVE_X:
            raise ValueError("MOVE_X must be read through axis()")

    @property
    def move_axis(self) -> float:
        return self.axis(InputAction.MOVE_X)

    @property
    def left_held(self) -> bool:
        return self.axis(InputAction.MOVE_X) < -InputSettings.AXIS_DEADZONE

    @property
    def right_held(self) -> bool:
        return self.axis(InputAction.MOVE_X) > InputSettings.AXIS_DEADZONE

    @property
    def guard_held(self) -> bool:
        return self.held(InputAction.GUARD)

    @property
    def guard_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.GUARD)

    @property
    def down_held(self) -> bool:
        return self.held(InputAction.MOVE_DOWN)

    @property
    def jump_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.JUMP)

    @property
    def jump_just_released(self) -> bool:
        return self.just_released(InputAction.JUMP)

    @property
    def dash_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.DASH)

    @property
    def attack1_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.ATTACK_1)

    @property
    def attack1_held(self) -> bool:
        return self.held(InputAction.ATTACK_1)

    @property
    def attack1_just_released(self) -> bool:
        return self.just_released(InputAction.ATTACK_1)

    @property
    def attack2_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.ATTACK_2)

    @property
    def attack2_held(self) -> bool:
        return self.held(InputAction.ATTACK_2)

    @property
    def attack2_just_released(self) -> bool:
        return self.just_released(InputAction.ATTACK_2)

    @property
    def attack3_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.ATTACK_3)

    @property
    def attack4_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.ATTACK_4)

    @property
    def reset_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.RESET)

    @property
    def special_attack_just_pressed(self) -> bool:
        return self.just_pressed(InputAction.SPECIAL_ATTACK)
