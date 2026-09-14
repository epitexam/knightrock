"""PhysicsSystem: entity integration stage of the level tick (audit F1.2 / §4).

Extracted from ``Level.update`` (audit §4: ``core/level/systems/physics_system``).
"""

from src.core.sprite_groups import SpriteGroups
from src.physics.movement import apply_moving_platform

__all__ = ["PhysicsSystem"]


class PhysicsSystem:
    """Carry platform riders, then run the entity and effect update passes.

    Order matters: ``apply_moving_platform`` reads the *current* platform
    rectangles, so it must run after :class:`PlatformSystem` moved them and
    before the entities integrate their own movement for the tick.
    """

    def __init__(self, groups: SpriteGroups) -> None:
        self.groups = groups

    def process(self, delta_time: float) -> None:
        """Apply the platform carry, then integrate entities and effects."""
        for entity in self.groups.entity_sprites:
            apply_moving_platform(entity, self.groups.moving_platforms)
        self.groups.entity_sprites.update(delta_time)
        self.groups.fx_sprites.update(delta_time)
