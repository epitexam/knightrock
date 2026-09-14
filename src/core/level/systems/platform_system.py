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
