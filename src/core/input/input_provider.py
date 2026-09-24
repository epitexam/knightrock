import pygame
from pygame.joystick import JoystickType

from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings
from src.core.input.input_state import InputState


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
        kb = self._bindings.keyboard
        buttons = self._bindings.gamepad_buttons
        axes = self._bindings.gamepad_axes
        keyboard_combos = self._bindings.keyboard_combos
        gamepad_combos = self._bindings.gamepad_combos
        self._current_joy_buttons = {}
        self._current_joy_axes = {}
        if self._joystick:
            for index in range(self._joystick.get_numbuttons()):
                self._current_joy_buttons[index] = bool(self._joystick.get_button(index))
            for index in range(self._joystick.get_numaxes()):
                self._current_joy_axes[index] = self._joystick.get_axis(index)

        held = {
            InputAction.MOVE_DOWN: bool(keys[kb["move_down"]]),
            InputAction.GUARD: bool(keys[kb["guard"]])
            or self._current_joy_buttons.get(buttons["guard"], False),
            InputAction.JUMP: bool(keys[kb["jump"]])
            or self._current_joy_buttons.get(buttons["jump"], False),
            InputAction.DASH: bool(keys[kb["dash"]])
            or self._current_joy_axes.get(axes["dash"], 0.0) > 0.5,
            InputAction.RESET: bool(keys[kb["reset"]])
            or self._current_joy_buttons.get(buttons["reset"], False),
        }
        special_keyboard = all(keys[key] for key in keyboard_combos["special_attack"])
        special_gamepad = all(
            self._current_joy_buttons.get(button, False)
            for button in gamepad_combos["special_attack"]
        )
        if special_keyboard or special_gamepad:
            held[InputAction.SPECIAL_ATTACK] = True
        else:
            for action, name in (
                (InputAction.ATTACK_1, "attack1"),
                (InputAction.ATTACK_2, "attack2"),
                (InputAction.ATTACK_3, "attack3"),
                (InputAction.ATTACK_4, "attack4"),
            ):
                held[action] = bool(keys[kb[name]]) or self._current_joy_buttons.get(
                    buttons[name], False
                )
        return InputState(
            move_axis=self._calculate_move_axis(keys, kb, axes),
            held_actions=frozenset(action for action, active in held.items() if active),
        )

    def _calculate_move_axis(self, keys: tuple[bool, ...], kb: dict, axes: dict) -> float:
        keyboard_axis = float(keys[kb["move_right"]]) - float(keys[kb["move_left"]])
        if keyboard_axis != 0.0:
            return keyboard_axis
        if self._joystick:
            analog = self._apply_deadzone(self._current_joy_axes.get(axes["move_x"], 0.0))
            if analog != 0.0:
                return analog
            hat = self._joystick.get_hat(0)[0]
            if hat != 0:
                return float(hat)
        return 0.0

    @staticmethod
    def _apply_deadzone(value: float, deadzone: float = 0.2) -> float:
        if abs(value) < deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - deadzone) / (1.0 - deadzone)
