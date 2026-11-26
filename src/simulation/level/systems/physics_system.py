"""PhysicsSystem: carry the platform riders, then move every entity.

The integration itself -- gravity, sub-stepped collision, landing -- runs in
each ``Entity.update``; this stage is where the tick hands it the clock. The
dust and shake that follow a move are :class:`FeedbackSystem`'s.
"""

from collections.abc import Sequence

from src.simulation.entities.entity import Entity
from src.simulation.physics.movement import apply_moving_platform
from src.simulation.sprite_groups import SpriteGroups

__all__ = ["PhysicsSystem"]


class PhysicsSystem:
    """Carry platform riders, then run the entity update pass.

    Order matters: ``apply_moving_platform`` reads the *current* platform
    rectangles, so it must run after :class:`PlatformSystem` moved them and
    before the entities integrate their own movement for the tick.
    """

    def __init__(self, groups: SpriteGroups) -> None:
        self.groups = groups

    def process(
        self,
        delta_time: float,
        world_delta: float | None = None,
        unslowed: Entity | None = None,
        fighters: Sequence[Entity] | None = None,
    ) -> None:
        """Apply the platform carry, then integrate the entities.

        Every entity runs on ``world_delta`` except ``unslowed``, which keeps
        the tick's own ``delta_time``: that is the whole of a slowed world, a
        fighter whose clock did not slow with it. Without a ``world_delta``
        there is one clock.
        """
        if world_delta is None:
            world_delta = delta_time
        if fighters is None:
            table = self.groups.movement_table
            fighters = (
                tuple(table.iter_entities())
                if table is not None
                else tuple(self.groups.entity_sprites)  # type: ignore[arg-type]
            )
        for entity in fighters:
            apply_moving_platform(entity, self.groups.moving_platforms)  # type: ignore[arg-type]
        # A copy: an update may remove its own entity from the group.
        for entity in fighters:
            entity.update(delta_time if entity is unslowed else world_delta)
