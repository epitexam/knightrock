import time
from collections.abc import Callable
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
    def __init__(
        self,
        bindings: InputBindings | None = None,
        clock: Callable[[], float] | None = None,
        joystick_reader: Callable[[], object] | None = None,
    ) -> None:
        self._bindings = bindings or InputBindings()
        self._active_axes: dict[tuple[int, int], InputAction] = {}
        self._axis_next_repeat: dict[tuple[int, int], float] = {}
        self._axis_last_value: dict[tuple[int, int], float] = {}
        self._active_hats: dict[tuple[int, int], tuple[InputAction | None, int, int]] = {}
        self._hat_next_repeat: dict[tuple[int, int], float] = {}
        self._clock = clock or time.monotonic
        self._joystick_reader = joystick_reader
        self._connected_joysticks: dict[int, object] = {}

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
            self.notify_joystick_removed(instance_id)
            return RoutedInput(
                InputAction.UI_CANCEL,
                InputDevice.GAMEPAD,
                variant="device_removed",
            )
        if event.type == pygame.JOYHATMOTION:
            return self._route_hat(
                getattr(event, "instance_id", 0),
                getattr(event, "hat", 0),
                getattr(event, "value", (0, 0)),
            )
        return self._route_axis(
            getattr(event, "instance_id", 0),
            getattr(event, "axis", 0),
            float(getattr(event, "value", 0.0)),
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

    def notify_joystick_connected(self, instance_id: int, joystick: object) -> None:
        self._connected_joysticks[instance_id] = joystick

    def notify_joystick_removed(self, instance_id: int) -> None:
        self._connected_joysticks.pop(instance_id, None)
        for key in tuple(self._active_axes):
            if key[0] == instance_id:
                self._active_axes.pop(key, None)
                self._axis_next_repeat.pop(key, None)
                self._axis_last_value.pop(key, None)
        for key in tuple(self._active_hats):
            if key[0] == instance_id:
                self._active_hats.pop(key, None)
                self._hat_next_repeat.pop(key, None)

    def reset(self) -> None:
        self._active_axes.clear()
        self._axis_next_repeat.clear()
        self._axis_last_value.clear()
        self._active_hats.clear()
        self._hat_next_repeat.clear()

    def set_bindings(self, bindings: InputBindings) -> None:
        self._bindings = bindings
        self.reset()

    def poll_repeats(self) -> list[RoutedInput]:
        now = self._clock()
        repeats: list[RoutedInput] = []
        repeats.extend(self._poll_axis_repeats(now))
        repeats.extend(self._poll_hat_repeats(now))
        return repeats

    def _poll_axis_repeats(self, now: float) -> list[RoutedInput]:
        repeats: list[RoutedInput] = []
        for (instance_id, axis), action in tuple(self._active_axes.items()):
            value = self._read_axis(instance_id, axis)
            if value is None:
                continue
            self._axis_last_value[(instance_id, axis)] = value
            if abs(value) <= InputSettings.UI_AXIS_RELEASE_THRESHOLD:
                self._active_axes.pop((instance_id, axis), None)
                self._axis_next_repeat.pop((instance_id, axis), None)
                continue
            if abs(value) < InputSettings.UI_AXIS_TRIGGER_THRESHOLD:
                continue
            next_repeat = self._axis_next_repeat.get((instance_id, axis))
            if next_repeat is None or now < next_repeat:
                continue
            self._axis_next_repeat[(instance_id, axis)] = now + InputSettings.UI_REPEAT_INTERVAL
            repeats.append(RoutedInput(action, InputDevice.GAMEPAD, value=value, variant="repeat"))
        return repeats

    def _poll_hat_repeats(self, now: float) -> list[RoutedInput]:
        repeats: list[RoutedInput] = []
        for (instance_id, hat), (action, x, y) in tuple(self._active_hats.items()):
            if action is None:
                continue
            live = self._read_hat(instance_id, hat)
            if live is None:
                # Pas de lecture live (test sans joystick, driver sans
                # get_hat) : on expire le bras au lieu de repeter a l'infini
                # sur la derniere valeur SDL connue.
                self._active_hats.pop((instance_id, hat), None)
                self._hat_next_repeat.pop((instance_id, hat), None)
                continue
            if live == (0, 0):
                self._active_hats.pop((instance_id, hat), None)
                self._hat_next_repeat.pop((instance_id, hat), None)
                continue
            if live is not None and live != (0, 0):
                live_action = self._hat_action(hat, live)
                if live_action is None:
                    continue
                action = live_action
                x, y = live
                self._active_hats[(instance_id, hat)] = (action, x, y)
            next_repeat = self._hat_next_repeat.get((instance_id, hat))
            if next_repeat is None or now < next_repeat:
                continue
            self._hat_next_repeat[(instance_id, hat)] = now + InputSettings.UI_REPEAT_INTERVAL
            value = float(x if action in (InputAction.UI_LEFT, InputAction.UI_RIGHT) else y)
            repeats.append(RoutedInput(action, InputDevice.GAMEPAD, value=value, variant="repeat"))
        return repeats

    def _resolve_joystick(self, instance_id: int) -> object | None:
        if instance_id in self._connected_joysticks:
            return self._connected_joysticks[instance_id]
        if self._joystick_reader is not None:
            try:
                joysticks = self._joystick_reader()
            except Exception:  # noqa: BLE001 - joystick flaky, jamais fatal
                return None
            if isinstance(joysticks, dict):
                joystick = joysticks.get(instance_id)
                if joystick is not None:
                    self._connected_joysticks[instance_id] = joystick
                return joystick
        return None

    def _read_axis(self, instance_id: int, axis: int) -> float | None:
        joystick = self._resolve_joystick(instance_id)
        if joystick is None:
            return None
        get_axis = getattr(joystick, "get_axis", None)
        if not callable(get_axis):
            return None
        try:
            return float(get_axis(axis))
        except Exception:  # noqa: BLE001 - joystick flaky, jamais fatal
            return None

    def _read_hat(self, instance_id: int, hat: int) -> tuple[int, int] | None:
        joystick = self._resolve_joystick(instance_id)
        if joystick is None:
            return None
        get_hat = getattr(joystick, "get_hat", None)
        if not callable(get_hat):
            return None
        try:
            return self._hat_xy(get_hat(hat))
        except Exception:  # noqa: BLE001 - joystick flaky, jamais fatal
            return None

    def _route_hat(self, instance_id: int, hat: int, value: object) -> RoutedInput | None:
        x, y = self._hat_xy(value)
        action = self._hat_action(hat, (x, y))
        key = (instance_id, hat)
        if action is None:
            self._active_hats.pop(key, None)
            self._hat_next_repeat.pop(key, None)
            return None
        previous = self._active_hats.get(key)
        now = self._clock()
        if previous is not None and previous[0] is action:
            if key not in self._hat_next_repeat:
                self._hat_next_repeat[key] = now + InputSettings.UI_REPEAT_INITIAL_DELAY
            return None
        self._active_hats[key] = (action, x, y)
        self._hat_next_repeat[key] = now + InputSettings.UI_REPEAT_INITIAL_DELAY
        return RoutedInput(action, InputDevice.GAMEPAD, value=float(x or y))

    def _route_axis(self, instance_id: int, axis: int, value: float) -> RoutedInput | None:
        key = (instance_id, axis)
        active = self._active_axes.get(key)
        if value == 0.0 or abs(value) <= InputSettings.UI_AXIS_RELEASE_THRESHOLD:
            self._active_axes.pop(key, None)
            self._axis_next_repeat.pop(key, None)
            self._axis_last_value.pop(key, None)
            if active is None:
                return None
            return RoutedInput(active, InputDevice.GAMEPAD, value=value, variant="release")
        action = self._axis_action(axis, value)
        if action is None or abs(value) < InputSettings.UI_AXIS_TRIGGER_THRESHOLD:
            self._active_axes.pop(key, None)
            self._axis_next_repeat.pop(key, None)
            self._axis_last_value.pop(key, None)
            return None
        self._axis_last_value[key] = value
        now = self._clock()
        if active == action:
            if key not in self._axis_next_repeat:
                self._axis_next_repeat[key] = now + InputSettings.UI_REPEAT_INITIAL_DELAY
            return None
        self._active_axes[key] = action
        self._axis_next_repeat[key] = now + InputSettings.UI_REPEAT_INITIAL_DELAY
        return RoutedInput(action, InputDevice.GAMEPAD, value=value)

    def _axis_action(self, axis: int, value: float) -> InputAction | None:
        for action, bound_axis in self._bindings.menu.gamepad_axes.items():
            if bound_axis != axis:
                continue
            if action in (InputAction.UI_LEFT, InputAction.UI_RIGHT):
                if (value < 0.0) == (action is InputAction.UI_LEFT):
                    return action
                continue
            if action in (InputAction.UI_UP, InputAction.UI_DOWN):
                is_up = value > 0.0 if self._bindings.menu.invert_y else value < 0.0
                if is_up == (action is InputAction.UI_UP):
                    return action
                continue
        return None

    def _hat_action(self, hat: int, value: tuple[int, int]) -> InputAction | None:
        x, y = value
        for action, bound_hat in self._bindings.menu.gamepad_hats.items():
            if bound_hat != hat:
                continue
            if y > 0 and action is InputAction.UI_UP:
                return action
            if y < 0 and action is InputAction.UI_DOWN:
                return action
            if x < 0 and action is InputAction.UI_LEFT:
                return action
            if x > 0 and action is InputAction.UI_RIGHT:
                return action
        return None

    @staticmethod
    def _hat_xy(value: object) -> tuple[int, int]:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            try:
                return int(value[0]), int(value[1])
            except TypeError, ValueError:
                return 0, 0
        return 0, 0
