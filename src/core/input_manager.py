"""
Core input state management for deterministic game logic.

Provides a state-based input representation decoupled from hardware.
This allows the Player entity to interact with a generic InputManager
that calculates 'just pressed' and 'just released' events, whether the
input originates from a local keyboard, a gamepad, or a network packet.
"""

from copy import copy
from typing import Optional

from src.core.input_provider import InputProvider, NullInputProvider
from src.core.input_state import InputState


class InputManager:
    """Abstraction layer for player inputs.

    Maintains the current and previous input states to provide event-driven
    properties like 'just_pressed' and 'just_released'. By relying on an
    InputProvider, this class is fully compatible with local and networked
    multiplayer architectures.
    """

    def __init__(self, provider: Optional[InputProvider] = None) -> None:
        """Initialize the InputManager with a default state and provider.

        Parameters
        ----------
        provider : Optional[InputProvider]
            The source of hardware or network inputs. Defaults to NullInputProvider.
        """
        self._provider: InputProvider = provider or NullInputProvider()
        self._current_state: InputState = InputState()
        self._prev_state: InputState = InputState()

    def set_provider(self, provider: InputProvider) -> None:
        """Assign a new input provider, such as a local hardware reader or network receiver.

        Parameters
        ----------
        provider : InputProvider
            The new input provider to use for polling states.
        """
        self._provider = provider

    def apply_remote_state(self, state: InputState) -> None:
        """Directly inject a new input state, used for networked remote players.

        This bypasses the provider, allowing server-side or network-received
        states to drive the logic without reading local hardware.

        Parameters
        ----------
        state : InputState
            The remote input state to apply for the current tick.
        """
        self._prev_state = copy(self._current_state)
        self._current_state = state

    def update(self) -> None:
        """Advance the input state by polling the provider and calculating deltas."""
        self._prev_state = copy(self._current_state)
        self._current_state = self._provider.poll()

    @property
    def move_axis(self) -> float:
        """Return the horizontal movement axis value."""
        return self._current_state.move_axis

    @property
    def left_held(self) -> bool:
        """Return True if the movement axis is towards the left."""
        return self._current_state.move_axis < -0.1

    @property
    def right_held(self) -> bool:
        """Return True if the movement axis is towards the right."""
        return self._current_state.move_axis > 0.1

    @property
    def block_held(self) -> bool:
        """Return True if the block action is held."""
        return self._current_state.block_held

    @property
    def jump_just_pressed(self) -> bool:
        """Return True if jump was pressed this tick."""
        return self._current_state.jump_held and not self._prev_state.jump_held

    @property
    def dash_just_pressed(self) -> bool:
        """Return True if dash was pressed this tick."""
        return self._current_state.dash_held and not self._prev_state.dash_held

    @property
    def attack1_just_pressed(self) -> bool:
        """Return True if attack 1 was pressed this tick."""
        return self._current_state.attack1_held and not self._prev_state.attack1_held

    @property
    def attack1_held(self) -> bool:
        """Return True if attack 1 is held."""
        return self._current_state.attack1_held

    @property
    def attack1_just_released(self) -> bool:
        """Return True if attack 1 was released this tick."""
        return not self._current_state.attack1_held and self._prev_state.attack1_held

    @property
    def attack2_just_pressed(self) -> bool:
        """Return True if attack 2 was pressed this tick."""
        return self._current_state.attack2_held and not self._prev_state.attack2_held

    @property
    def attack2_held(self) -> bool:
        """Return True if attack 2 is held."""
        return self._current_state.attack2_held

    @property
    def attack2_just_released(self) -> bool:
        """Return True if attack 2 was released this tick."""
        return not self._current_state.attack2_held and self._prev_state.attack2_held

    @property
    def attack3_just_pressed(self) -> bool:
        """Return True if attack 3 was pressed this tick."""
        return self._current_state.attack3_held and not self._prev_state.attack3_held

    @property
    def attack4_just_pressed(self) -> bool:
        """Return True if attack 4 was pressed this tick."""
        return self._current_state.attack4_held and not self._prev_state.attack4_held

    @property
    def reset_just_pressed(self) -> bool:
        """Return True if reset was pressed this tick."""
        return self._current_state.reset_held and not self._prev_state.reset_held

    @property
    def special_attack_just_pressed(self) -> bool:
        """Return True if the special attack combination was pressed this tick."""
        return self._current_state.special_attack_held and not self._prev_state.special_attack_held
