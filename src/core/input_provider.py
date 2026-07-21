"""
Hardware-specific input collection using Pygame.

Provides classes responsible for reading raw input data from local devices
(keyboard and gamepad) and converting them into a generic InputState. This
isolates Pygame dependencies from the core game logic and state machine.
"""

from typing import Optional

import pygame
from pygame.joystick import JoystickType

from src.core.input_state import InputState
from src.core.input_bindings import InputBindings


class InputProvider:
    """Abstract base class for input sources."""

    def poll(self) -> InputState:
        """Retrieve the current input state from the source."""
        raise NotImplementedError


class NullInputProvider(InputProvider):
    """Default provider that yields an empty input state."""

    def poll(self) -> InputState:
        """Return a default, empty InputState."""
        return InputState()


class LocalInputProvider(InputProvider):
    """Reads hardware inputs from keyboard and gamepad using Pygame.

    Manages joystick connections, deadzones, and custom bindings, translating
    raw hardware states into the generic InputState structure.
    """

    def __init__(self, bindings: Optional[InputBindings] = None) -> None:
        """Initialize the LocalInputProvider with custom or default bindings.

        Parameters
        ----------
        bindings : Optional[InputBindings]
            The hardware codes mapping. Defaults to InputBindings() if not provided.
        """
        self._bindings: InputBindings = bindings or InputBindings()
        self._joystick: Optional[JoystickType] = None
        self._current_joy_buttons: dict[int, bool] = {}
        self._current_joy_axes: dict[int, float] = {}

    def connect_joystick(self, joystick: JoystickType) -> None:
        """Handle the connection of a new joystick.

        Parameters
        ----------
        joystick : JoystickType
            The Pygame joystick object that was connected.
        """
        self._joystick = joystick

    def disconnect_joystick(self, instance_id: int) -> None:
        """Handle the disconnection of the active joystick.

        Parameters
        ----------
        instance_id : int
            The instance ID of the disconnected joystick.
        """
        if self._joystick and self._joystick.get_instance_id() == instance_id:
            self._joystick = None

    def reassign_joystick(self, joysticks: dict[int, JoystickType]) -> None:
        """Reassign the active joystick from available devices.

        Parameters
        ----------
        joysticks : dict[int, JoystickType]
            A dictionary of currently connected joysticks.
        """
        if not self._joystick and joysticks:
            self._joystick = list(joysticks.values())[0]

    def poll(self) -> InputState:
        """Read local hardware states and return an InputState snapshot."""
        keys = pygame.key.get_pressed()
        kb = self._bindings.keyboard
        btns = self._bindings.gamepad_buttons
        axes = self._bindings.gamepad_axes

        self._current_joy_buttons = {}
        self._current_joy_axes = {}

        if self._joystick:
            for i in range(self._joystick.get_numbuttons()):
                self._current_joy_buttons[i] = bool(
                    self._joystick.get_button(i))
            for i in range(self._joystick.get_numaxes()):
                self._current_joy_axes[i] = self._joystick.get_axis(i)

        state = InputState()
        state.move_axis = self._calculate_move_axis(keys, kb, axes)
        state.block_held = keys[kb["block"]] or self._current_joy_buttons.get(
            btns["block"], False)
        state.jump_held = keys[kb["jump"]] or self._current_joy_buttons.get(
            btns["jump"], False)
        state.dash_held = keys[kb["dash"]] or self._current_joy_axes.get(
            axes["dash"], 0.0) > 0.5
        state.attack1_held = keys[kb["attack1"]] or self._current_joy_buttons.get(
            btns["attack1"], False)
        state.attack2_held = keys[kb["attack2"]] or self._current_joy_buttons.get(
            btns["attack2"], False)
        state.attack3_held = keys[kb["attack3"]] or self._current_joy_buttons.get(
            btns["attack3"], False)
        state.attack4_held = keys[kb["attack4"]] or self._current_joy_buttons.get(
            btns["attack4"], False)
        state.reset_held = keys[kb["reset"]] or self._current_joy_buttons.get(
            btns["reset"], False)

        return state

    def _calculate_move_axis(self, keys: tuple[bool, ...], kb: dict, axes: dict) -> float:
        """Calculate the horizontal movement axis from keyboard and gamepad.

        Prioritizes keyboard input over gamepad analog sticks and D-pads.

        Parameters
        ----------
        keys : tuple[bool, ...]
            The current state of all keyboard keys from Pygame.
        kb : dict
            The keyboard bindings dictionary.
        axes : dict
            The gamepad axes bindings dictionary.

        Returns
        -------
        float
            The normalized horizontal axis value (-1.0 to 1.0).
        """
        kb_axis = float(keys[kb["move_right"]]) - float(keys[kb["move_left"]])

        if kb_axis != 0.0:
            return kb_axis

        if self._joystick:
            raw = self._current_joy_axes.get(axes["move_x"], 0.0)
            analog = self._apply_deadzone(raw)
            if analog != 0.0:
                return analog
            hat = self._joystick.get_hat(0)[0]
            if hat != 0:
                return float(hat)

        return 0.0

    @staticmethod
    def _apply_deadzone(value: float, deadzone: float = 0.2) -> float:
        """Apply a radial deadzone to an analog axis value.

        Parameters
        ----------
        value : float
            The raw axis value from the gamepad.
        deadzone : float
            The threshold below which input is ignored.

        Returns
        -------
        float
            The normalized axis value after applying the deadzone.
        """
        if abs(value) < deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - deadzone) / (1.0 - deadzone)
