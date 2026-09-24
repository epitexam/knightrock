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
                InputAction.UI_POINTER_DOWN,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type == pygame.MOUSEBUTTONUP and getattr(event, "button", 0) == 1:
            return RoutedInput(
                InputAction.UI_POINTER_UP,
                InputDevice.MOUSE,
                position=tuple(getattr(event, "pos", (0, 0))),
            )
        if event.type in (
            pygame.JOYBUTTONDOWN,
            pygame.JOYDEVICEREMOVED,
            pygame.JOYHATMOTION,
            pygame.JOYAXISMOTION,
        ):
            return self._route_gamepad(event)
        return None

    def _route_gamepad(self, event: pygame.event.Event) -> RoutedInput | None:
        if event.type == pygame.JOYBUTTONDOWN:
            return self._route_gamepad_button(getattr(event, "button", -1))
        if event.type == pygame.JOYDEVICEREMOVED:
            instance_id = getattr(event, "instance_id", 0)
            for key in tuple(self._active_axes):
                if key[0] == instance_id:
                    self._active_axes.pop(key, None)
            return RoutedInput(
                InputAction.UI_CANCEL,
                InputDevice.GAMEPAD,
                variant="device_removed",
            )
        if event.type == pygame.JOYHATMOTION:
            return self._route_hat(getattr(event, "hat", 0), getattr(event, "value", (0, 0)))
        return self._route_axis(
            getattr(event, "instance_id", 0),
            getattr(event, "axis", -1),
            getattr(event, "value", 0.0),
        )

    def _route_keyboard(self, key: int) -> RoutedInput | None:
        if key == self._bindings.menu.new_game_key:
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

    def _route_hat(self, hat: int, value: tuple[int, int]) -> RoutedInput | None:
        action = self._hat_action(hat, value)
        if action is None:
            return None
        return RoutedInput(action, InputDevice.GAMEPAD, value=float(value[0] or value[1]))

    def _route_axis(self, instance_id: int, axis: int, value: float) -> RoutedInput | None:
        key = (instance_id, axis)
        active = self._active_axes.get(key)
        if value == 0.0 or abs(value) <= InputSettings.UI_AXIS_RELEASE_THRESHOLD:
            self._active_axes.pop(key, None)
            if active is None:
                return None
            return RoutedInput(active, InputDevice.GAMEPAD, value=value, variant="release")
        action = self._axis_action(axis, value)
        if action is None:
            return None
        if abs(value) < InputSettings.UI_AXIS_TRIGGER_THRESHOLD:
            return None
        self._active_axes[key] = action
        variant = "repeat" if active == action else None
        return RoutedInput(action, InputDevice.GAMEPAD, value=value, variant=variant)

    def _axis_action(self, axis: int, value: float) -> InputAction | None:
        for action, bound_axis in self._bindings.menu.gamepad_axes.items():
            if bound_axis != axis:
                continue
            if action in (InputAction.UI_LEFT, InputAction.UI_RIGHT):
                if (value < 0.0) == (action is InputAction.UI_LEFT):
                    return action
                continue
            if action in (InputAction.UI_UP, InputAction.UI_DOWN):
                if (value < 0.0) == (action is InputAction.UI_UP):
                    return action
                continue
        return None

    def _hat_action(self, hat: int, value: tuple[int, int]) -> InputAction | None:
        x, y = value
        for action, bound_hat in self._bindings.menu.gamepad_hats.items():
            if bound_hat != hat:
                continue
            if y < 0 and action is InputAction.UI_UP:
                return action
            if y > 0 and action is InputAction.UI_DOWN:
                return action
            if x < 0 and action is InputAction.UI_LEFT:
                return action
            if x > 0 and action is InputAction.UI_RIGHT:
                return action
        return None
