"""Stand-ins shaped like the real objects, shared by the tests that need them.

A stand-in that drifts from the object it imitates tests nothing: the wall-jump
lock was dead in the game for months because its tests used stand-ins with a
shape the real Player did not have.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pygame

from src.core.rendering.render_hints import RenderHints

#: Where the real Player keeps each controller field: flat test name -> attribute
#: on the controller. Flat names keep the tests short; the stand-in stores them
#: where the game reads them.
_CONTROLLER_FIELDS: dict[str, dict[str, str]] = {
    "jump": {
        "jump_buffer_timer": "jump_buffer_timer",
        "coyote_timer": "coyote_timer",
        "midair_jumps_left": "midair_jumps_left",
        "wall_jumps_left": "wall_jumps_left",
        "jump_height": "jump_height",
        "wall_jump_height": "wall_jump_height",
    },
    "guard": {
        "guard_posture": "posture",
        "guard_posture_max": "max_posture",
        "guard_lockout_timer": "lockout_timer",
        "guard_riposte_timer": "riposte_timer",
    },
    "dash": {
        "dash_charges": "charges",
        "max_dash_charges": "max_charges",
        "dash_penalty_timer": "penalty_timer",
        "dash_recharge_timer": "recharge_timer",
        "dash_speed": "speed",
        "dash_duration": "duration",
        "dash_friction": "friction",
        "dash_requested": "requested",
    },
}


def player_shape(**fields: Any) -> SimpleNamespace:
    """A player stand-in with the real Player's ``jump``/``guard``/``dash`` controllers.

    Pass a controller (``dash=DashController(...)``) to use it; the flat fields
    for that controller are set on it.
    """
    controllers = {name: fields.pop(name, None) or SimpleNamespace() for name in _CONTROLLER_FIELDS}
    for name, mapping in _CONTROLLER_FIELDS.items():
        for flat, attribute in mapping.items():
            if flat in fields:
                setattr(controllers[name], attribute, fields.pop(flat))
    return SimpleNamespace(**fields, **controllers)


class FighterSprite(pygame.sprite.Sprite):
    """A sprite with what the renderer and the FX pass read on every ``Entity``.

    ``entity_sprites`` holds entities, so the code that walks it reads these
    fields directly. A stand-in put in that group starts from this shape and
    overrides what its test is about.
    """

    faction = "enemy"
    facing_right = True
    is_dead = False
    is_invincible = False
    dash = None
    turn_lead_px = 0.0
    turn_skew_px = 0.0

    def __init__(self, *groups: Any) -> None:
        super().__init__(*groups)
        self.render_hints = RenderHints()
        self.state_machine = SimpleNamespace(current_state_name=None)
