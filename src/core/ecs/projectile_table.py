"""Dense flight state for projectiles, mirrored from the pooled sprites.

During the migration the pooled ``Projectile`` remains the presentation proxy,
but every value the simulation reads also lives in a dense table keyed by a
generation-checked handle. The mirror is asserted on every tick in test builds;
once both paths agree, the systems can read the table directly and the sprite
can be reduced to a draw adapter.
"""

from __future__ import annotations

from typing import Any

from src.core.ecs.table import DenseTable, Handle
from src.entities.projectile import Projectile

_COLUMNS = (
    "owner_id",
    "faction",
    "config",
    "hitbox",
    "velocity",
    "contact_shape",
    "previous_shape",
    "previous_rect",
    "life",
    "active",
    "targets_hit",
    "proxy",
)


class ProjectileTable(DenseTable):
    """The flight columns, plus the mapping from a slot to its sprite proxy."""

    def __init__(self) -> None:
        super().__init__(_COLUMNS)

    def write(self, slot: int, projectile: Projectile) -> None:
        """Copy one pooled projectile's live state into the dense row."""
        self.column("owner_id")[slot] = projectile.id
        self.column("faction")[slot] = projectile.faction
        self.column("config")[slot] = projectile.config
        self.column("hitbox")[slot] = projectile.hitbox.copy()
        self.column("velocity")[slot] = projectile.velocity.copy()
        self.column("contact_shape")[slot] = projectile.contact_shape
        self.column("previous_shape")[slot] = projectile._previous_contact_shape
        self.column("previous_rect")[slot] = (
            None
            if projectile._previous_contact_rect is None
            else projectile._previous_contact_rect.copy()
        )
        self.column("life")[slot] = projectile.life
        self.column("active")[slot] = projectile.active
        self.column("targets_hit")[slot] = set(projectile.targets_hit)
        self.column("proxy")[slot] = projectile

    def assert_mirror(self, slot: int) -> None:
        """Fail loudly if the proxy and the dense row disagree."""
        projectile: Projectile = self.column("proxy")[slot]
        assert self.column("owner_id")[slot] == projectile.id
        assert self.column("faction")[slot] == projectile.faction
        assert self.column("config")[slot] == projectile.config
        assert self.column("hitbox")[slot] == projectile.hitbox
        assert self.column("velocity")[slot] == projectile.velocity
        assert self.column("contact_shape")[slot] == projectile.contact_shape
        assert self.column("previous_shape")[slot] == projectile._previous_contact_shape
        assert self.column("previous_rect")[slot] == projectile._previous_contact_rect
        assert self.column("life")[slot] == projectile.life
        assert self.column("active")[slot] == projectile.active
        assert self.column("targets_hit")[slot] == set(projectile.targets_hit)

    def handle_of(self, slot: int) -> Handle:
        return self.handle_at(slot)

    def proxy_of(self, slot: int) -> Any:
        return self.column("proxy")[slot]
