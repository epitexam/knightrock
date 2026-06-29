"""
Unified keyboard and gamepad input management.
Exposes boolean states and "just pressed" / "just released" events.
"""

from typing import Optional

import pygame
from pygame.joystick import Joystick, JoystickType


class InputManager:
    """Abstraction of inputs for the player."""

    def __init__(self) -> None:
        self._joystick: Optional[JoystickType] = (
            Joystick(0) if pygame.joystick.get_count() > 0 else None
        )

        self._key_prev: dict[int, bool] = {}
        self._button_prev: dict[int, bool] = {}
        self._trigger_prev: dict[int, bool] = {}

        self._jump_just_pressed = False
        self._dash_just_pressed = False
        self._attack1_just_pressed = False
        self._attack2_just_pressed = False
        self._attack3_just_pressed = False
        self._attack4_just_pressed = False
        self._reset_just_pressed = False

        self._attack1_held = False
        self._attack1_just_released = False

    def update(self) -> None:
        """Updates the input state for the current frame.
        Calculates 'just pressed' and 'just released' events for all actions.
        """
        keys = pygame.key.get_pressed()
        joy = self._joystick

        def update_key(key: int) -> bool:
            current = bool(keys[key])
            previous = self._key_prev.get(key, False)
            just = current and not previous
            self._key_prev[key] = current
            return just

        def update_key_release(key: int) -> bool:
            current = bool(keys[key])
            previous = self._key_prev.get(key, False)
            released = not current and previous
            self._key_prev[key] = current
            return released

        def update_button(btn: int) -> bool:
            if not joy:
                return False
            current = bool(joy.get_button(btn))
            previous = self._button_prev.get(btn, False)
            just = current and not previous
            self._button_prev[btn] = current
            return just

        def update_button_release(btn: int) -> bool:
            if not joy:
                return False
            current = bool(joy.get_button(btn))
            previous = self._button_prev.get(btn, False)
            released = not current and previous
            self._button_prev[btn] = current
            return released

        def update_trigger(axis: int) -> bool:
            if not joy:
                return False
            current = joy.get_axis(axis) > 0.5
            previous = self._trigger_prev.get(axis, False)
            just = current and not previous
            self._trigger_prev[axis] = current
            return just

        def update_trigger_release(axis: int) -> bool:
            if not joy:
                return False
            current = joy.get_axis(axis) > 0.5
            previous = self._trigger_prev.get(axis, False)
            released = not current and previous
            self._trigger_prev[axis] = current
            return released

        jump_key = update_key(pygame.K_SPACE)
        jump_btn = update_button(0)
        self._jump_just_pressed = jump_key or jump_btn

        dash_key = update_key(pygame.K_LSHIFT)
        dash_trig = update_trigger(2)
        self._dash_just_pressed = dash_key or dash_trig

        attack1_key_pressed = update_key(pygame.K_a)
        attack1_btn_pressed = update_button(1)
        self._attack1_just_pressed = attack1_key_pressed or attack1_btn_pressed

        self._attack1_held = bool(keys[pygame.K_a]) or (
            joy and joy.get_button(1))

        attack1_key_released = update_key_release(pygame.K_a)
        attack1_btn_released = update_button_release(1)
        self._attack1_just_released = attack1_key_released or attack1_btn_released

        attack2_key = update_key(pygame.K_s)
        attack2_btn = update_button(2)
        self._attack2_just_pressed = attack2_key or attack2_btn

        attack3_key = update_key(pygame.K_d)
        attack3_btn = update_button(3)
        self._attack3_just_pressed = attack3_key or attack3_btn

        attack4_key = update_key(pygame.K_f)
        attack4_btn = update_button(5)
        self._attack4_just_pressed = attack4_key or attack4_btn

        reset_key = update_key(pygame.K_r)
        reset_btn = update_button(7)
        self._reset_just_pressed = reset_key or reset_btn

    @staticmethod
    def _apply_deadzone(value: float, deadzone: float = 0.2) -> float:
        if abs(value) < deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - deadzone) / (1.0 - deadzone)

    @property
    def move_axis(self) -> float:
        """Horizontal axis: -1 (left) to 1 (right)."""
        keys = pygame.key.get_pressed()
        kb_axis = float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT])

        if kb_axis != 0.0:
            return kb_axis

        if self._joystick:
            raw = self._joystick.get_axis(0)
            analog = self._apply_deadzone(raw)
            if analog != 0.0:
                return analog
            hat = self._joystick.get_hat(0)[0]
            if hat != 0:
                return float(hat)
        return 0.0

    @property
    def left_held(self) -> bool:
        return self.move_axis < -0.1

    @property
    def right_held(self) -> bool:
        return self.move_axis > 0.1

    @property
    def block_held(self) -> bool:
        keys = pygame.key.get_pressed()
        if keys[pygame.K_q]:
            return True
        if self._joystick:
            return self._joystick.get_button(4)
        return False

    @property
    def jump_just_pressed(self) -> bool:
        return self._jump_just_pressed

    @property
    def dash_just_pressed(self) -> bool:
        return self._dash_just_pressed

    @property
    def attack1_just_pressed(self) -> bool:
        return self._attack1_just_pressed

    @property
    def attack1_held(self) -> bool:
        return self._attack1_held

    @property
    def attack1_just_released(self) -> bool:
        return self._attack1_just_released

    @property
    def attack2_just_pressed(self) -> bool:
        return self._attack2_just_pressed

    @property
    def attack3_just_pressed(self) -> bool:
        return self._attack3_just_pressed

    @property
    def attack4_just_pressed(self) -> bool:
        return self._attack4_just_pressed

    @property
    def reset_just_pressed(self) -> bool:
        return self._reset_just_pressed
