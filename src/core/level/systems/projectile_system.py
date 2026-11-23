"""ProjectileSystem: pooled flying hitboxes (audit Phase 5 #3).

Extracted as a world stage like the other ``core/level/systems`` stages.
Targets are resolved through the unified
:class:`~src.core.level.systems.contact_system.ContactSystem`, which
owns the per-tick grid prune (O(n . k) instead of projectiles x entities;
exhaustive without a grid) and the shared hit resolution: ranged hits go
through :class:`~src.combat.hit_resolver.HitResolver` so they share armor,
stagger and finisher rules with melee.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from src.combat.combatant_protocol import Combatant
from src.combat.shapes import ShapeKind, shape_aabb_intersects, swept_intersects_aabb
from src.core.ecs.projectile_table import ProjectileTable
from src.core.ecs.table import Handle
from src.core.level.systems.contact_system import (
    ContactSystem,
    GuardEvent,
    ImpactEvent,
    OffensiveBox,
)
from src.core.object_pool import ObjectPool
from src.core.sprite_groups import SpriteGroups
from src.entities.id_factory import IdFactory
from src.entities.projectile import Projectile, ProjectileConfig
from src.physics.entity_grid import EntityGrid
from src.physics.spatial_hash import SpatialHash, collider_box

__all__ = ["ProjectileSystem"]


def _reset_projectile(projectile: Projectile) -> None:
    projectile.reset()


def _record_target(projectile: Projectile) -> Callable[[Combatant], None]:
    """Adapter: the unified pipeline records targets, the pool records ids."""

    def record(target: Combatant) -> None:
        projectile.targets_hit.add(target.id)

    return record


class ProjectileSystem:
    """Spawn, integrate and resolve pooled projectiles once per tick."""

    def __init__(
        self,
        groups: SpriteGroups,
        pool: ObjectPool[Projectile] | None = None,
        spatial_hash: SpatialHash | None = None,
        contact_system: ContactSystem | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.groups = groups
        factory = id_factory if id_factory is not None else IdFactory()
        self.pool: ObjectPool[Projectile] = (
            pool
            if pool is not None
            else ObjectPool(lambda: Projectile(id_factory=factory), reset=_reset_projectile)
        )
        self.spatial_hash = spatial_hash
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )
        self.guard_events: list[GuardEvent] = []
        self.impact_events: list[ImpactEvent] = []
        # The dense row is the seed of the ECS storage for projectiles. The
        # pooled sprite stays the draw proxy until the presentation adapter
        # lands; every tick writes both and the test build asserts they agree.
        self.table = ProjectileTable()
        self._slot_of_proxy: dict[int, int] = {}
        self._handle_of_proxy: dict[int, Handle] = {}

    def spawn(
        self,
        config: ProjectileConfig,
        pos: tuple[float, float],
        velocity: tuple[float, float],
        faction: str,
    ) -> Projectile:
        """Take a pooled projectile and put it into flight."""
        projectile = self.pool.acquire()
        projectile.launch(config, pos, velocity, faction)
        self.groups.projectile_sprites.add(projectile)
        self.groups.all_sprites.add(projectile)

        proxy_id = id(projectile)
        handle = self._handle_of_proxy.get(proxy_id, (projectile.id, 0))
        slot = self.table.acquire(handle)
        self.table.write(slot, projectile)
        self._slot_of_proxy[proxy_id] = slot
        self._handle_of_proxy[proxy_id] = handle
        return projectile

    def rebuild_table_from_groups(self) -> None:
        """Re-seed dense rows after a rollback restored the sprite groups."""
        self.table = ProjectileTable()
        self._slot_of_proxy.clear()
        self._handle_of_proxy.clear()
        for shot in self.groups.projectile_sprites:
            if not isinstance(shot, Projectile):
                continue
            handle = (shot.id, 0)
            slot = self.table.acquire(handle)
            self.table.write(slot, shot)
            self._slot_of_proxy[id(shot)] = slot
            self._handle_of_proxy[id(shot)] = handle

    def process(
        self,
        delta_time: float,
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Advance every projectile and resolve contacts."""
        self.guard_events.clear()
        self.impact_events.clear()
        if delta_time <= 0.0:
            return
        for projectile in list(self.groups.projectile_sprites):
            if not isinstance(projectile, Projectile):
                continue
            projectile.capture_contact_origin()
            projectile.update(delta_time)
            slot = self._slot_of_proxy[id(projectile)]
            self.table.write(slot, projectile)
            self.table.assert_mirror(slot)
            if projectile.is_dead:
                self._release(projectile)
                continue
            if self._hit_wall(projectile):
                self._release(projectile)
                continue
            self._resolve_contacts(projectile, entity_grid)

    def _hit_wall(self, projectile: Projectile) -> bool:
        """True when the swept flying box overlaps static collision geometry."""
        swept_rect = projectile.swept_contact_rect()
        shape_sweeps = projectile.swept_contact_shapes()
        for sprite in (
            self.spatial_hash.get_nearby(swept_rect)
            if self.spatial_hash is not None
            else self.groups.collision_sprites
        ):
            box = collider_box(sprite)
            if box is None:
                continue
            box = pygame.FRect(box)
            shape_hit = any(
                (
                    shape_aabb_intersects(shape.current, box)
                    if shape.previous is None
                    else swept_intersects_aabb(shape.previous, shape.current, box)
                )
                for shape in shape_sweeps
                if shape.current.kind is not ShapeKind.AABB
            )
            if shape_hit or swept_rect.colliderect(box):
                return True
        return False

    def _resolve_contacts(
        self,
        projectile: Projectile,
        entity_grid: EntityGrid | None,
    ) -> None:
        """Emit the projectile's offensive box into the unified pipeline.

        Legacy semantics preserved: ``HitResolver`` decides whether the
        contact lands, the projectile remembers the target, and a
        single-hit projectile is released (stopping after the first
        contact) while a piercing one keeps flying.
        """
        config = projectile.config
        box = OffensiveBox(
            box=projectile.hitbox,
            swept=(projectile.swept_contact_rect(),),
            hit=config.hit,
            swept_shapes=(
                projectile.swept_contact_shapes() if config.shape is not ShapeKind.AABB else ()
            ),
            faction=projectile.faction,
            owner_id=projectile.id,
            can_contact=projectile.can_contact,
            kind="projectile",
            attacker=projectile,
            stop_after_first=not config.pierce,
            record_contact=_record_target(projectile),
        )
        outcome = self.contact_system.resolve((box,), self.groups.entity_sprites, entity_grid)
        self.guard_events.extend(outcome.guard_events)
        self.impact_events.extend(outcome.impact_events)
        if outcome.metrics.contacts and not config.pierce:
            self._release(projectile)

    def _release(self, projectile: Projectile) -> None:
        proxy_id = id(projectile)
        slot = self._slot_of_proxy.pop(proxy_id)
        released = self.table.release(slot)
        self._handle_of_proxy[proxy_id] = (released[0], released[1] + 1)
        projectile.kill()
        self.pool.release(projectile)
