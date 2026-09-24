from dataclasses import dataclass
from enum import StrEnum

import pygame

from src.core.input.input_actions import InputAction
from src.core.input.input_bindings import InputBindings
from src.core.settings import Input as InputSettings


class InputDevice(StrEnum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    GAMEPAD = "gamepad"


@dataclass(frozen=True)
class RoutedInput:
    action: InputAction
    device: InputDevice
    position: tuple[int, int] | None = None
    value: float | None = None
    variant: str | None = None


class EventRouter:
    def __init__(self, bindings: InputBindings | None = None) -> None:
        self._bindings = bindings or InputBindings()
        self._active_axes: dict[tuple[int, int], InputAction] = {}

    def route(self, event: pygame.event.Event) -> RoutedInput | None:
        if event.type == pygame.KEYDOWN:
            return self._route_keyboard(getattr(event, "key", -1))
        if event.type == pygame.MOUSEMOTION:
            return RoutedInput(
                InputAction.UI_POINTER_MOVE,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 0) == 1:
            return RoutedInput(
                InputAction.UI_CONFIRM,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type == pygame.MOUSEBUTTONUP and getattr(event, "button", 0) == 1:
            return RoutedInput(
                InputAction.UI_POINTER_UP,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type == pygame.JOYBUTTONDOWN:
            return self._route_gamepad_button(getattr(event, "button", -1))
        if event.type == pygame.JOYHATMOTION:
            return self._route_hat(getattr(event, "value", (0, 0)))
        if event.type == pygame.JOYAXISMOTION:
            return self._route_axis(
                getattr(event, "instance_id", 0),
                getattr(event, "axis", -1),
                getattr(event, "value", 0.0),
            )
        return None

    def _route_keyboard(self, key: int) -> RoutedInput | None:
        if key == pygame.K_n:
            return RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD, variant="new_game")
        for action, binding in self._bindings.menu.keyboard.items():
            keys = binding if isinstance(binding, tuple) else (binding,)
            if key in keys:
                return RoutedInput(action, InputDevice.KEYBOARD)
        return None

    def _route_gamepad_button(self, button: int) -> RoutedInput | None:
        for action, binding in self._bindings.menu.gamepad_buttons.items():
            if binding == button:
                return RoutedInput(action, InputDevice.GAMEPAD)
        return None

    def _route_hat(self, value: tuple[int, int]) -> RoutedInput | None:
        x, y = value
        if y < 0:
            action = InputAction.UI_UP
        elif y > 0:
            action = InputAction.UI_DOWN
        elif x < 0:
            action = InputAction.UI_LEFT
        elif x > 0:
            action = InputAction.UI_RIGHT
        else:
            return None
        return RoutedInput(action, InputDevice.GAMEPAD, value=float(x or y))

    def _route_axis(self, instance_id: int, axis: int, value: float) -> RoutedInput | None:
        action = self._axis_action(axis, value)
        if action is None:
            return None
        key = (instance_id, axis)
        active = self._active_axes.get(key)
        if value == 0.0 or abs(value) <= InputSettings.UI_AXIS_RELEASE_THRESHOLD:
            self._active_axes.pop(key, None)
            if active != action:
                return None
            return RoutedInput(action, InputDevice.GAMEPAD, value=value)
        if abs(value) < InputSettings.UI_AXIS_TRIGGER_THRESHOLD:
            return None
        self._active_axes[key] = action
        if active == action:
            return None
        return RoutedInput(action, InputDevice.GAMEPAD, value=value)

    @staticmethod
    def _axis_action(axis: int, value: float) -> InputAction | None:
        if axis == 0:
            return InputAction.UI_LEFT if value < 0.0 else InputAction.UI_RIGHT
        if axis == 1:
            return InputAction.UI_UP if value < 0.0 else InputAction.UI_DOWN
        return None
