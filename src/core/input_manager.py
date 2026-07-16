"""
Unified keyboard and gamepad input management.

Provides a snapshot-based input state to ensure deterministic behavior
within fixed timesteps. Exposes boolean states and 'just pressed' /
'just released' events.
"""

from typing import Optional

import pygame
from pygame.joystick import JoystickType


class InputManager:
    """Abstraction layer for player inputs, handling keyboard and gamepad."""

    def __init__(self) -> None:
        """Initialize the InputManager and default input states."""
        self._joystick: Optional[JoystickType] = None

        self._current_keys = pygame.key.get_pressed()
        self._prev_keys = self._current_keys

        self._current_joy_buttons: dict[int, bool] = {}
        self._prev_joy_buttons: dict[int, bool] = {}

        self._current_joy_axes: dict[int, float] = {}
        self._prev_joy_axes: dict[int, float] = {}

        self._jump_just_pressed = False
        self._dash_just_pressed = False
        self._attack1_just_pressed = False
        self._attack2_just_pressed = False
        self._attack3_just_pressed = False
        self._attack4_just_pressed = False
        self._reset_just_pressed = False

        self._attack1_held = False
        self._attack1_just_released = False

        self._attack2_held = False
        self._attack2_just_released = False

    def connect_joystick(self, joystick: JoystickType) -> None:
        """Handle the connection of a new joystick."""
        self._joystick = joystick
        self._prev_joy_buttons.clear()
        self._prev_joy_axes.clear()

    def disconnect_joystick(self, instance_id: int) -> None:
        """Handle the disconnection of the active joystick."""
        if self._joystick and self._joystick.get_instance_id() == instance_id:
            self._joystick = None
            self._prev_joy_buttons.clear()
            self._prev_joy_axes.clear()

    def reassign_joystick(self, joysticks: dict[int, JoystickType]) -> None:
        """Reassign the active joystick from available devices if the current one was disconnected."""
        if not self._joystick and joysticks:
            self._joystick = list(joysticks.values())[0]
            self._prev_joy_buttons.clear()
            self._prev_joy_axes.clear()

    def update(self) -> None:
        """Update the input state for the current logic tick by calculating deltas."""
        self._prev_keys = self._current_keys
        self._current_keys = pygame.key.get_pressed()

        self._prev_joy_buttons = self._current_joy_buttons.copy()
        self._prev_joy_axes = self._current_joy_axes.copy()
        self._current_joy_buttons = {}
        self._current_joy_axes = {}

        if self._joystick:
            for i in range(self._joystick.get_numbuttons()):
                self._current_joy_buttons[i] = bool(self._joystick.get_button(i))
            for i in range(self._joystick.get_numaxes()):
                self._current_joy_axes[i] = self._joystick.get_axis(i)

        self._jump_just_pressed = self._is_key_just_pressed(pygame.K_SPACE) or self._is_button_just_pressed(0)
        self._dash_just_pressed = self._is_key_just_pressed(pygame.K_LSHIFT) or self._is_trigger_just_pressed(2)

        self._attack1_just_pressed = self._is_key_just_pressed(pygame.K_a) or self._is_button_just_pressed(1)
        self._attack1_held = self._is_key_held(pygame.K_a) or self._is_button_held(1)
        self._attack1_just_released = self._is_key_just_released(pygame.K_a) or self._is_button_just_released(1)

        self._attack2_just_pressed = self._is_key_just_pressed(pygame.K_s) or self._is_button_just_pressed(2)
        self._attack2_held = self._is_key_held(pygame.K_s) or self._is_button_held(2)
        self._attack2_just_released = self._is_key_just_released(pygame.K_s) or self._is_button_just_released(2)

        self._attack3_just_pressed = self._is_key_just_pressed(pygame.K_d) or self._is_button_just_pressed(3)
        self._attack4_just_pressed = self._is_key_just_pressed(pygame.K_f) or self._is_button_just_pressed(5)
        self._reset_just_pressed = self._is_key_just_pressed(pygame.K_r) or self._is_button_just_pressed(7)

    def _is_key_just_pressed(self, key: int) -> bool:
        """Check if a keyboard key was pressed this tick."""
        return self._current_keys[key] and not self._prev_keys[key]

    def _is_key_just_released(self, key: int) -> bool:
        """Check if a keyboard key was released this tick."""
        return not self._current_keys[key] and self._prev_keys[key]

    def _is_key_held(self, key: int) -> bool:
        """Check if a keyboard key is currently held."""
        return bool(self._current_keys[key])

    def _is_button_just_pressed(self, btn: int) -> bool:
        """Check if a gamepad button was pressed this tick."""
        return self._current_joy_buttons.get(btn, False) and not self._prev_joy_buttons.get(btn, False)

    def _is_button_just_released(self, btn: int) -> bool:
        """Check if a gamepad button was released this tick."""
        return not self._current_joy_buttons.get(btn, False) and self._prev_joy_buttons.get(btn, False)

    def _is_button_held(self, btn: int) -> bool:
        """Check if a gamepad button is currently held."""
        return self._current_joy_buttons.get(btn, False)

    def _is_trigger_just_pressed(self, axis: int) -> bool:
        """Check if a gamepad trigger axis passed the activation threshold this tick."""
        current = self._current_joy_axes.get(axis, 0.0) > 0.5
        previous = self._prev_joy_axes.get(axis, 0.0) > 0.5
        return current and not previous

    @staticmethod
    def _apply_deadzone(value: float, deadzone: float = 0.2) -> float:
        """Apply a radial deadzone to an analog axis value."""
        if abs(value) < deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - deadzone) / (1.0 - deadzone)

    @property
    def move_axis(self) -> float:
        """Horizontal axis: -1.0 (left) to 1.0 (right), prioritizing keyboard over gamepad."""
        kb_axis = float(self._current_keys[pygame.K_RIGHT]) - float(self._current_keys[pygame.K_LEFT])

        if kb_axis != 0.0:
            return kb_axis

        if self._joystick:
            raw = self._current_joy_axes.get(0, 0.0)
            analog = self._apply_deadzone(raw)
            if analog != 0.0:
                return analog
            hat = self._joystick.get_hat(0)[0]
            if hat != 0:
                return float(hat)

        return 0.0

    @property
    def left_held(self) -> bool:
        """Check if the movement axis is towards the left."""
        return self.move_axis < -0.1

    @property
    def right_held(self) -> bool:
        """Check if the movement axis is towards the right."""
        return self.move_axis > 0.1

    @property
    def block_held(self) -> bool:
        """Check if the block action is held via keyboard or gamepad."""
        if self._current_keys[pygame.K_q]:
            return True
        if self._joystick:
            return self._current_joy_buttons.get(4, False)
        return False

    @property
    def jump_just_pressed(self) -> bool:
        """Check if jump was just pressed."""
        return self._jump_just_pressed

    @property
    def dash_just_pressed(self) -> bool:
        """Check if dash was just pressed."""
        return self._dash_just_pressed

    @property
    def attack1_just_pressed(self) -> bool:
        """Check if attack 1 was just pressed."""
        return self._attack1_just_pressed

    @property
    def attack1_held(self) -> bool:
        """Check if attack 1 is held."""
        return self._attack1_held

    @property
    def attack1_just_released(self) -> bool:
        """Check if attack 1 was just released."""
        return self._attack1_just_released

    @property
    def attack2_just_pressed(self) -> bool:
        """Check if attack 2 was just pressed."""
        return self._attack2_just_pressed

    @property
    def attack2_held(self) -> bool:
        """Check if attack 2 is held."""
        return self._attack2_held

    @property
    def attack2_just_released(self) -> bool:
        """Check if attack 2 was just released."""
        return self._attack2_just_released

    @property
    def attack3_just_pressed(self) -> bool:
        """Check if attack 3 was just pressed."""
        return self._attack3_just_pressed

    @property
    def attack4_just_pressed(self) -> bool:
        """Check if attack 4 was just pressed."""
        return self._attack4_just_pressed

    @property
    def reset_just_pressed(self) -> bool:
        """Check if reset was just pressed."""
        return self._reset_just_pressed