"""Backward-compatible path for :mod:`src.simulation.physics`."""

from src.simulation.physics.collisions import resolve_collisions
from src.simulation.physics.movement import (
    apply_horizontal_movement,
    apply_moving_platform,
    move_entity,
    resolve_jump,
)
from src.simulation.physics.spatial_hash import SpatialHash
from src.simulation.physics.velocity import (
    apply_slide_friction,
    apply_velocity_friction,
    lerp_velocity,
)

__all__ = [
    "SpatialHash",
    "apply_horizontal_movement",
    "apply_moving_platform",
    "apply_slide_friction",
    "apply_velocity_friction",
    "lerp_velocity",
    "move_entity",
    "resolve_collisions",
    "resolve_jump",
]
