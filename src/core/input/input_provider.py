from collections.abc import Mapping, Sequence

import pygame
from pygame.joystick import JoystickType

from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import ActionMap, AxisMap, ButtonMap, ComboMap, InputBindings
from src.core.input.input_state import InputState
from src.core.settings import Input as InputSettings


class InputProvider:
    def poll(self) -> InputState:
        raise NotImplementedError


class NullInputProvider(InputProvider):
    def poll(self) -> InputState:
        return InputState()


class LocalInputProvider(InputProvider):
    def __init__(self, bindings: InputBindings | None = None) -> None:
        self._bindings = bindings or InputBindings()
        self._joystick: JoystickType | None = None
        self._current_joy_buttons: dict[int, bool] = {}
        self._current_joy_axes: dict[int, float] = {}

    def connect_joystick(self, joystick: JoystickType) -> None:
        self._joystick = joystick

    def disconnect_joystick(self, instance_id: int) -> None:
        if self._joystick and self._joystick.get_instance_id() == instance_id:
            self._joystick = None

    def reassign_joystick(self, joysticks: dict[int, JoystickType]) -> None:
        if not self._joystick and joysticks:
            self._joystick = next(iter(joysticks.values()))

    def poll(self) -> InputState:
        keys = pygame.key.get_pressed()
        gameplay = self._bindings.gameplay
        self._current_joy_buttons = {}
        self._current_joy_axes = {}
        if self._joystick:
            for index in range(self._joystick.get_numbuttons()):
                self._current_joy_buttons[index] = bool(self._joystick.get_button(index))
            for index in range(self._joystick.get_numaxes()):
                self._current_joy_axes[index] = self._joystick.get_axis(index)

        held = {
            InputAction.MOVE_DOWN: self._key_held(keys, gameplay.keyboard, InputAction.MOVE_DOWN),
            InputAction.GUARD: self._key_held(keys, gameplay.keyboard, InputAction.GUARD)
            or self._button_held(gameplay.gamepad_buttons, InputAction.GUARD),
            InputAction.JUMP: self._key_held(keys, gameplay.keyboard, InputAction.JUMP)
            or self._button_held(gameplay.gamepad_buttons, InputAction.JUMP),
            InputAction.DASH: self._key_held(keys, gameplay.keyboard, InputAction.DASH)
            or self._axis_value(gameplay.gamepad_axes, InputAction.DASH)
            > InputSettings.DASH_AXIS_THRESHOLD,
            InputAction.RESET: self._key_held(keys, gameplay.keyboard, InputAction.RESET)
            or self._button_held(gameplay.gamepad_buttons, InputAction.RESET),
        }
        special_keyboard = self._combo_held(
            keys, gameplay.keyboard_combos, InputAction.SPECIAL_ATTACK
        )
        special_gamepad = self._combo_held(
            self._current_joy_buttons, gameplay.gamepad_combos, InputAction.SPECIAL_ATTACK
        )
        if special_keyboard or special_gamepad:
            held[InputAction.SPECIAL_ATTACK] = True
        else:
            for action in (
                InputAction.ATTACK_1,
                InputAction.ATTACK_2,
                InputAction.ATTACK_3,
                InputAction.ATTACK_4,
            ):
                held[action] = self._key_held(keys, gameplay.keyboard, action) or (
                    self._button_held(gameplay.gamepad_buttons, action)
                )
        return InputState(
            move_axis=self._calculate_move_axis(keys),
            held_actions=frozenset(action for action, active in held.items() if active),
        )

    def _calculate_move_axis(self, keys: tuple[bool, ...]) -> float:
        bindings = self._bindings.gameplay
        axis_keys = bindings.keyboard[InputAction.MOVE_X]
        if not isinstance(axis_keys, tuple):
            raise ValueError("MOVE_X must bind two keyboard keys")
        left_key, right_key = axis_keys
        keyboard_axis = float(keys[right_key]) - float(keys[left_key])
        if keyboard_axis != 0.0:
            return keyboard_axis
        if self._joystick:
            raw = self._current_joy_axes.get(bindings.gamepad_axes[InputAction.MOVE_X], 0.0)
            analog = self._apply_deadzone(raw)
            if analog != 0.0:
                return analog
            hat = self._joystick.get_hat(0)[0]
            if hat != 0:
                return float(hat)
        return 0.0

    def _key_held(self, keys: Sequence[bool], bindings: ActionMap, action: InputAction) -> bool:
        key = bindings[action]
        return any(keys[code] for code in (key if isinstance(key, tuple) else (key,)))

    def _button_held(self, bindings: ButtonMap, action: InputAction) -> bool:
        return self._current_joy_buttons.get(bindings[action], False)

    def _axis_value(self, bindings: AxisMap, action: InputAction) -> float:
        return self._current_joy_axes.get(bindings[action], 0.0)

    @staticmethod
    def _combo_held(
        current: Sequence[bool] | Mapping[int, bool], bindings: ComboMap, action: InputAction
    ) -> bool:
        combo = bindings.get(action, ())
        if isinstance(current, Mapping):
            return bool(combo) and all(current.get(code, False) for code in combo)
        return bool(combo) and all(current[code] for code in combo)

    @staticmethod
    def _apply_deadzone(value: float) -> float:
        value = max(-1.0, min(1.0, value))
        if abs(value) < InputSettings.AXIS_DEADZONE:
            return 0.0
        magnitude = (abs(value) - InputSettings.AXIS_DEADZONE) / (1.0 - InputSettings.AXIS_DEADZONE)
        return magnitude if value > 0.0 else -magnitude
