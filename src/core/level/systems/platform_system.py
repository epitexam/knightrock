"""PlatformSystem: moving-platform stage of the level tick (audit F1.2 / §4).

Extracted from ``Level.update`` so the level becomes a facade over its
systems (audit §4: ``core/level/systems/platform_system``).
"""

from src.core.sprite_groups import SpriteGroups
from src.physics.spatial_hash import SpatialHash

__all__ = ["PlatformSystem"]


class PlatformSystem:
    """Advance the moving platforms and re-bucket them in the collision grid.

    The platforms move first each tick and the spatial hash must follow:
    entity collision queries read the grid, so a platform that is not
    re-bucketed would still be found at its previous position (PERF-01).
    """

    def __init__(self, groups: SpriteGroups, spatial_hash: SpatialHash) -> None:
        self.groups = groups
        self.spatial_hash = spatial_hash

    def process(self, delta_time: float) -> None:
        """Move the platforms, then re-bucket them for collision queries."""
        self.groups.moving_platforms.update(delta_time)
        self.spatial_hash.update_all(self.groups.moving_platforms)
        self._push_entities()

    def _push_entities(self) -> None:
        """Shove entities a platform moved into this tick (pads are solid).

        Entities already overlapping a platform before it moved are riders:
        the carry in ``PhysicsSystem`` handles them.  Only entities the pad
        *moved into* are pushed, along the pad's dominant axis and by at
        most the pad's own displacement, so a push can never teleport.
        """
        for platform in self.groups.moving_platforms:
            dx = platform.hitbox.x - platform.old_hitbox.x
            dy = platform.hitbox.y - platform.old_hitbox.y
            if dx == 0 and dy == 0:
                continue
            for entity in self.groups.entity_sprites:
                if not entity.hitbox.colliderect(platform.hitbox):
                    continue
                if entity.hitbox.colliderect(platform.old_hitbox):
                    continue
                if abs(dx) >= abs(dy):
                    entity.hitbox.x += dx
                else:
                    entity.hitbox.y += dy
                entity.sync_rects()
