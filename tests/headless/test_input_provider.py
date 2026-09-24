import pygame
import pytest

from src.core.input.input_actions import InputAction
from src.core.input.input_manager import InputManager
from src.core.input.input_provider import LocalInputProvider, resolve_move_axis
from src.core.settings import Input as InputSettings


class FakeJoystick:
    def __init__(self, instance_id: int = 1) -> None:
        self._instance_id = instance_id
        self.axes = [0.0, 0.0, 0.0]
        self.buttons = [False] * 8
        self.hat = (0, 0)

    def get_instance_id(self) -> int:
        return self._instance_id

    def get_numbuttons(self) -> int:
        return len(self.buttons)

    def get_button(self, index: int) -> bool:
        return self.buttons[index]

    def get_numaxes(self) -> int:
        return len(self.axes)

    def get_axis(self, index: int) -> float:
        return self.axes[index]

    def get_hat(self, _index: int) -> tuple[int, int]:
        return self.hat


def _press(*keys: int) -> dict[int, bool]:
    return dict.fromkeys(keys, True)


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    *keys: int,
) -> tuple[LocalInputProvider, FakeJoystick]:
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: _press(*keys))
    provider = LocalInputProvider()
    joystick = FakeJoystick()
    provider.connect_joystick(joystick)  # type: ignore[arg-type]
    return provider, joystick


def test_neutral_socd_cancels_opposing_directions() -> None:
    assert resolve_move_axis(-1.0, 0.0, 0.0) == -1.0
    assert resolve_move_axis(-1.0, 0.5, 0.0) == 0.0
    assert resolve_move_axis(0.0, 0.5, -1.0) == 0.0
    assert resolve_move_axis(1.0, 0.5, 1.0) == 1.0


def test_keyboard_opposition_is_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, joystick = _provider(monkeypatch, pygame.K_LEFT)
    joystick.axes[0] = 0.8

    assert provider.poll().move_axis == 0.0


def test_gamepad_horizontal_axis_uses_single_deadzone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(InputSettings, "AXIS_DEADZONE", 0.25)
    provider, joystick = _provider(monkeypatch)
    joystick.axes[0] = 0.5
    manager = InputManager(provider)

    manager.update()

    assert manager.axis(InputAction.MOVE_X) == pytest.approx(1.0 / 3.0)


def test_analog_axis_is_saturated(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, joystick = _provider(monkeypatch)
    joystick.axes[0] = 2.0

    assert provider.poll().move_axis == 1.0


def test_down_uses_keyboard_then_analog_then_hat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, joystick = _provider(monkeypatch, pygame.K_DOWN)
    assert InputAction.MOVE_DOWN in provider.poll().held_actions

    monkeypatch.setattr(pygame.key, "get_pressed", lambda: _press())
    joystick.axes[1] = 1.0
    assert InputAction.MOVE_DOWN in provider.poll().held_actions

    joystick.axes[1] = 0.0
    joystick.hat = (0, -1)
    assert InputAction.MOVE_DOWN in provider.poll().held_actions

    joystick.hat = (0, 1)
    assert InputAction.MOVE_DOWN not in provider.poll().held_actions


def test_gamepad_buttons_dash_reset_and_combo(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, joystick = _provider(monkeypatch)
    joystick.buttons[0] = True
    joystick.buttons[1] = True
    joystick.buttons[3] = True
    joystick.buttons[7] = True
    joystick.axes[2] = 1.0

    actions = provider.poll().held_actions

    assert InputAction.JUMP in actions
    assert InputAction.DASH in actions
    assert InputAction.RESET in actions
    assert InputAction.SPECIAL_ATTACK in actions
    assert InputAction.ATTACK_1 not in actions
    assert InputAction.ATTACK_3 not in actions


def test_keyboard_and_gamepad_combos_are_logical_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _ = _provider(monkeypatch, pygame.K_g, pygame.K_h)

    actions = provider.poll().held_actions

    assert InputAction.SPECIAL_ATTACK in actions
    assert InputAction.ATTACK_1 not in actions
    assert InputAction.ATTACK_2 not in actions


def test_disconnect_and_reassign_joystick(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, active = _provider(monkeypatch)
    replacement = FakeJoystick(2)

    provider.disconnect_joystick(active.get_instance_id())
    assert provider.poll().move_axis == 0.0

    provider.reassign_joystick({replacement.get_instance_id(): replacement})  # type: ignore[dict-item]
    replacement.axes[0] = 1.0
    assert provider.poll().move_axis == 1.0
