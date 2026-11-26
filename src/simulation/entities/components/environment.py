"""Ground probes shared by every fighter, extracted from ``Entity``.

The scanner owns no state: it asks its owner for geometry and the spatial
index. Moving these pure queries out of the entity leaves the tick template and
the combat facade with one less responsibility, without changing a call site --
``Entity.is_at_ledge`` and ``Entity.find_landing_ahead`` delegate to it.
"""

from __future__ import annotations

from typing import Any, Protocol

import pygame

from src.simulation.physics.collisions import get_nearby_sprites
from src.simulation.physics.spatial_hash import SpatialHash, collider_box
from src.simulation.settings import EnemyJump, Ledge


class EnvironmentOwner(Protocol):
    """The geometry an environment probe needs from its fighter."""

    hitbox: pygame.FRect
    on_surface: dict[str, bool]
    spatial_hash: SpatialHash | None
    collision_sprites: Any

    def _walk_direction(self) -> float: ...


class EnvironmentScanner:
    """Answer ledge and landing questions about the owner's surroundings."""

    def __init__(self, owner: EnvironmentOwner) -> None:
        self.owner = owner

    def is_at_ledge(self) -> bool:
        """Return True when grounded with no ground ahead of the walk.

        A probe hangs off the front foot (``Ledge.PROBE_AHEAD_PX`` wide,
        ``Ledge.PROBE_DROP_PX`` deep): any collider inside means ground,
        nothing inside means void. The walk direction leads (locomotion
        states set ``move_axis`` before probing); facing is only the idle
        fallback. Airborne entities are falling, not at a ledge.
        Deterministic (no randomness); shared by every entity.
        """
        owner = self.owner
        if not owner.on_surface.get("floor", False):
            return False
        ahead_right = owner._walk_direction() > 0.0
        ahead = Ledge.PROBE_AHEAD_PX
        skin = Ledge.PROBE_SKIN_PX
        drop = Ledge.PROBE_DROP_PX
        if ahead_right:
            probe = pygame.FRect(owner.hitbox.right, owner.hitbox.bottom - skin, ahead, skin + drop)
        else:
            probe = pygame.FRect(
                owner.hitbox.left - ahead, owner.hitbox.bottom - skin, ahead, skin + drop
            )
        nearby = get_nearby_sprites(
            owner,  # type: ignore[arg-type]
            spatial_hash=owner.spatial_hash,
            collision_sprites=owner.collision_sprites,
        )
        for sprite in nearby:
            box = collider_box(sprite)
            if box is not None and probe.colliderect(box):
                return False
        return True

    def find_landing_ahead(
        self, max_dist: float, max_rise: float, max_drop: float
    ) -> tuple[float, float] | None:
        """Next landable ground ahead: (distance from the front foot, drop).

        Samples forward in ``GAP_SCAN_STEP_PX`` increments: the first
        collider whose top sits between ``max_rise`` above and ``max_drop``
        below the feet wins, and its depth below the feet is returned
        alongside the distance. Walls (tops out of band) never match.
        Returns None past ``max_dist``. Deterministic; shared by every entity.
        """
        owner = self.owner
        if max_dist <= 0.0:
            return None
        direction = owner._walk_direction()
        front = owner.hitbox.right if direction > 0.0 else owner.hitbox.left
        boxes: list[Any] = []
        for sprite in get_nearby_sprites(
            owner,  # type: ignore[arg-type]
            spatial_hash=owner.spatial_hash,
            collision_sprites=owner.collision_sprites,
        ):
            box = collider_box(sprite)
            if box is not None:
                boxes.append(box)
        step = EnemyJump.GAP_SCAN_STEP_PX
        distance = max(step, Ledge.PROBE_AHEAD_PX + step)
        while distance <= max_dist:
            center = front + direction * distance
            sample = pygame.FRect(
                center - 2.0, owner.hitbox.bottom - max_rise, 4.0, max_rise + max_drop
            )
            for box in boxes:
                if (
                    sample.colliderect(box)
                    and box.top >= owner.hitbox.bottom - max_rise
                    and box.top <= owner.hitbox.bottom + max_drop
                ):
                    return distance, box.top - owner.hitbox.bottom
            distance += step
        return None
