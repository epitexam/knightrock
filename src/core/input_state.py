"""
Data structures for representing input states.

Defines the InputState dataclass used to transfer input snapshots
between hardware providers, network layers, and the game logic.
"""

from dataclasses import dataclass


@dataclass
class InputState:
    """Represents a snapshot of all player inputs for a single logic tick.

    Attributes
    ----------
    move_axis : float
        Horizontal movement axis, typically ranging from -1.0 to 1.0.
    block_held : bool
        Whether the block action is currently held.
    jump_held : bool
        Whether the jump action is currently held.
    dash_held : bool
        Whether the dash action is currently held.
    attack1_held : bool
        Whether the primary attack action is currently held.
    attack2_held : bool
        Whether the secondary attack action is currently held.
    attack3_held : bool
        Whether the tertiary attack action is currently held.
    attack4_held : bool
        Whether the quaternary attack action is currently held.
    reset_held : bool
        Whether the reset action is currently held.
    """
    move_axis: float = 0.0
    block_held: bool = False
    jump_held: bool = False
    dash_held: bool = False
    attack1_held: bool = False
    attack2_held: bool = False
    attack3_held: bool = False
    attack4_held: bool = False
    reset_held: bool = False