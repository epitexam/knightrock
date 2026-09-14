"""Physics helpers for entity movement, collisions and detection."""

from .collisions import (
    get_nearby_sprites,
    hitbox_collide,
    resolve_collisions,
    update_contact_state,
)
from .entity_grid import EntityGrid, overlapping_pairs
from .gravity import apply_entity_gravity
from .movement import (
    apply_horizontal_movement,
    apply_moving_platform,
    move_entity,
    resolve_jump,
)
from .platforms import update_moving_platform
from .spatial_hash import (
    QUERY_MARGIN_PX,
    RectHashable,
    SpatialHash,
    SpatialHashable,
    SpatialHashMember,
)
from .velocity import apply_velocity_friction, lerp_velocity

__all__ = [
    "EntityGrid",
    "SpatialHash",
    "SpatialHashable",
    "RectHashable",
    "SpatialHashMember",
    "QUERY_MARGIN_PX",
    "apply_entity_gravity",
    "apply_horizontal_movement",
    "apply_moving_platform",
    "apply_velocity_friction",
    "get_nearby_sprites",
    "hitbox_collide",
    "lerp_velocity",
    "move_entity",
    "overlapping_pairs",
    "resolve_collisions",
    "resolve_jump",
    "update_contact_state",
    "update_moving_platform",
]
