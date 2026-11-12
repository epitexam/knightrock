"""PhysicsSystem: carry the platform riders, then move every entity.

The integration itself -- gravity, sub-stepped collision, landing -- runs in
each ``Entity.update``; this stage is where the tick hands it the clock. The
dust and shake that follow a move are :class:`FeedbackSystem`'s.
"""

from src.core.sprite_groups import SpriteGroups
from src.physics.movement import apply_moving_platform

__all__ = ["PhysicsSystem"]


class PhysicsSystem:
    """Carry platform riders, then run the entity update pass.

    Order matters: ``apply_moving_platform`` reads the *current* platform
    rectangles, so it must run after :class:`PlatformSystem` moved them and
    before the entities integrate their own movement for the tick.
    """

    def __init__(self, groups: SpriteGroups) -> None:
        self.groups = groups

    def process(self, delta_time: float) -> None:
        """Apply the platform carry, then integrate the entities."""
        for entity in self.groups.entity_sprites:
            apply_moving_platform(entity, self.groups.moving_platforms)
        self.groups.entity_sprites.update(delta_time)
