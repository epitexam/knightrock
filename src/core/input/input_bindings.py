"""
Default input bindings for keyboard and gamepad.

Defines the mapping between abstract actions and physical hardware codes.
These mappings can be customized to support user-defined keybinds.
"""

import pygame
from dataclasses import dataclass, field


@dataclass
class InputBindings:
    """Represents the hardware codes mapped to abstract game actions.

    Attributes
    ----------
    keyboard : dict[str, int]
        Mapping of action names to Pygame keyboard key codes (e.g., pygame.K_SPACE).
    gamepad_buttons : dict[str, int]
        Mapping of action names to gamepad button indices.
    gamepad_axes : dict[str, int]
        Mapping of action names to gamepad axis indices.
    keyboard_combos : dict[str, list[int]]
        Mapping of combo action names to a list of required keyboard keys.
    gamepad_combos : dict[str, list[int]]
        Mapping of combo action names to a list of required gamepad buttons.
    """

    keyboard: dict[str, int] = field(default_factory=lambda: {
        "move_left": pygame.K_LEFT,
        "move_right": pygame.K_RIGHT,
        "jump": pygame.K_SPACE,
        "dash": pygame.K_LSHIFT,
        "attack1": pygame.K_a,
        "attack2": pygame.K_s,
        "attack3": pygame.K_d,
        "attack4": pygame.K_f,
        "block": pygame.K_q,
        "reset": pygame.K_r,
    })

    gamepad_buttons: dict[str, int] = field(default_factory=lambda: {
        "jump": 0,
        "attack1": 1,
        "attack2": 2,
        "attack3": 3,
        "block": 4,
        "attack4": 5,
        "reset": 7,
    })

    gamepad_axes: dict[str, int] = field(default_factory=lambda: {
        "move_x": 0,
        "dash": 2,
    })

    keyboard_combos: dict[str, list[int]] = field(default_factory=lambda: {
        "special_attack": [pygame.K_g, pygame.K_h],
    })

    gamepad_combos: dict[str, list[int]] = field(default_factory=lambda: {
        "special_attack": [1, 3],  # attack1 + attack3 (B + Y on Xbox)
    })
