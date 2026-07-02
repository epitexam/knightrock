"""Physics helpers for entity movement, collisions and detection."""

from .collisions import (
    get_nearby_sprites,
    hitbox_collide,
    resolve_collisions,
    update_contact_state,
)
from .contact_damage import ContactDamageSystem
from .gravity import apply_entity_gravity
from .movement import (
    apply_horizontal_movement,
    apply_moving_platform,
    move_entity,
    resolve_jump,
)
from .platforms import update_moving_platform
from .separation import SeparationSystem
from .velocity import apply_velocity_friction, lerp_velocity

__all__ = [
    "ContactDamageSystem",
    "SeparationSystem",
    "apply_entity_gravity",
    "apply_horizontal_movement",
    "apply_moving_platform",
    "apply_velocity_friction",
    "get_nearby_sprites",
    "hitbox_collide",
    "lerp_velocity",
    "move_entity",
    "resolve_collisions",
    "resolve_jump",
    "update_contact_state",
    "update_moving_platform",
]
