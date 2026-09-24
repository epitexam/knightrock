from collections.abc import Mapping, Sequence

import pygame
from pygame.joystick import JoystickType

from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import ActionMap, AxisMap, ButtonMap, ComboMap, InputBindings
from src.core.input.input_state import InputState
from src.core.settings import Input as InputSettings


def resolve_move_axis(keyboard_axis: float, analog_axis: float, hat_axis: float) -> float:
    directions = {
        direction
        for direction in (
            _axis_direction(keyboard_axis),
            _axis_direction(analog_axis),
            _axis_direction(hat_axis),
        )
        if direction != 0
    }
    if len(directions) > 1:
        return 0.0
    if keyboard_axis != 0.0:
        return keyboard_axis
    if analog_axis != 0.0:
        return analog_axis
    return hat_axis


def _axis_direction(value: float) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0


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
        self._current_joy_hats: dict[int, tuple[float, float]] = {}

    def set_bindings(self, bindings: InputBindings) -> None:
        self._bindings = bindings

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
        self._current_joy_hats = {}
        if self._joystick:
            for index in range(self._joystick.get_numbuttons()):
                self._current_joy_buttons[index] = bool(self._joystick.get_button(index))
            for index in range(self._joystick.get_numaxes()):
                self._current_joy_axes[index] = self._joystick.get_axis(index)
            for index in set(gameplay.gamepad_hats.values()):
                self._current_joy_hats[index] = self._joystick.get_hat(index)

        down_held = self._key_held(keys, gameplay.keyboard, InputAction.MOVE_DOWN)
        if not down_held:
            down_axis = self._apply_deadzone(
                self._axis_value(gameplay.gamepad_axes, InputAction.MOVE_DOWN)
            )
            down_held = down_axis > 0.0
        if not down_held:
            hat = self._hat_value(gameplay.gamepad_hats, InputAction.MOVE_DOWN)
            down_held = hat[1] > 0

        held = {
            InputAction.MOVE_DOWN: down_held,
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

    def _calculate_move_axis(self, keys: Sequence[bool] | Mapping[int, bool]) -> float:
        bindings = self._bindings.gameplay
        axis_keys = bindings.keyboard[InputAction.MOVE_X]
        if not isinstance(axis_keys, tuple):
            raise ValueError("MOVE_X must bind two keyboard keys")
        left_key, right_key = axis_keys
        keyboard_axis = float(self._key_value(keys, right_key)) - float(
            self._key_value(keys, left_key)
        )
        analog = self._apply_deadzone(self._axis_value(bindings.gamepad_axes, InputAction.MOVE_X))
        hat = float(self._hat_value(bindings.gamepad_hats, InputAction.MOVE_X)[0])
        return resolve_move_axis(keyboard_axis, analog, hat)

    @staticmethod
    def _key_value(keys: Sequence[bool] | Mapping[int, bool], key: int) -> bool:
        if isinstance(keys, Mapping):
            return keys.get(key, False)
        return keys[key]

    def _key_held(
        self, keys: Sequence[bool] | Mapping[int, bool], bindings: ActionMap, action: InputAction
    ) -> bool:
        key = bindings[action]
        codes = key if isinstance(key, tuple) else (key,)
        return any(self._key_value(keys, code) for code in codes)

    def _button_held(self, bindings: ButtonMap, action: InputAction) -> bool:
        return self._current_joy_buttons.get(bindings[action], False)

    def _axis_value(self, bindings: AxisMap, action: InputAction) -> float:
        return self._current_joy_axes.get(bindings[action], 0.0)

    def _hat_value(self, bindings: ButtonMap, action: InputAction) -> tuple[float, float]:
        return self._current_joy_hats.get(bindings[action], (0.0, 0.0))

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
