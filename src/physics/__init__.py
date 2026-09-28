"""Physics helpers for entity movement, collisions and detection.

The physics layer is a real aggregation point -- eight call sites import from
this package rather than from a leaf module -- so it keeps re-exporting. The
set is the eight names below and nothing else: the other twelve it used to
carry (``EntityGrid``, ``overlapping_pairs``, ``apply_entity_gravity``,
``apply_jump_cut``, ``update_moving_platform``, ``update_contact_state``,
``hitbox_collide``, ``get_nearby_sprites`` and the spatial-hash types) are
imported from their own modules by their only consumers.
"""

from .collisions import resolve_collisions
from .movement import (
    apply_horizontal_movement,
    apply_moving_platform,
    move_entity,
    resolve_jump,
)
from .spatial_hash import SpatialHash
from .velocity import apply_velocity_friction, lerp_velocity

__all__ = [
    "SpatialHash",
    "apply_horizontal_movement",
    "apply_moving_platform",
    "apply_velocity_friction",
    "lerp_velocity",
    "move_entity",
    "resolve_collisions",
    "resolve_jump",
]
