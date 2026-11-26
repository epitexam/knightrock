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

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pygame

from src.simulation.combat.combatant_protocol import Combatant
from src.simulation.combat.shapes import (
    ShapeKind,
    SweptShape,
    shape_aabb_intersects,
    swept_intersects_aabb,
)
from src.simulation.combat.sweep import swept_box
from src.simulation.ecs.projectile_table import ProjectileTable
from src.simulation.ecs.table import Handle
from src.simulation.entities.entity import Entity
from src.simulation.entities.id_factory import IdFactory
from src.simulation.entities.projectile import Projectile, ProjectileConfig
from src.simulation.level.systems.contact_system import (
    ContactSystem,
    GuardEvent,
    ImpactEvent,
    OffensiveBox,
)
from src.simulation.object_pool import ObjectPool
from src.simulation.physics.entity_grid import EntityGrid
from src.simulation.physics.spatial_hash import SpatialHash, collider_box
from src.simulation.sprite_groups import SpriteGroups

__all__ = ["ProjectileSystem"]


def _reset_projectile(projectile: Projectile) -> None:
    projectile.reset()


def _record_target(targets: set[str], projectile: Projectile) -> Callable[[Combatant], None]:
    """The pipeline records a hit in the dense row and in the draw proxy."""

    def record(target: Combatant) -> None:
        targets.add(target.id)
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

    def handle_for(self, projectile: Projectile) -> Handle:
        """The generation-checked identity of a live projectile's dense row."""
        return self.table.handle_of(self._slot_of_proxy[id(projectile)])

    def rebuild_table_from_groups(self, handles: Mapping[int, Handle] | None = None) -> None:
        """Re-seed dense rows after a rollback restored the sprite groups."""
        self.table = ProjectileTable()
        self._slot_of_proxy.clear()
        self._handle_of_proxy.clear()
        for shot in self.groups.projectile_sprites:
            if not isinstance(shot, Projectile):
                continue
            handle = (shot.id, 0) if handles is None else handles[id(shot)]
            slot = self.table.acquire(handle)
            self.table.write(slot, shot)
            self._slot_of_proxy[id(shot)] = slot
            self._handle_of_proxy[id(shot)] = handle

    def process(
        self,
        delta_time: float,
        entity_grid: EntityGrid | None = None,
        fighters: Sequence[Entity] | None = None,
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
            if self._hit_wall(slot):
                self._release(projectile)
                continue
            self._resolve_contacts(slot, entity_grid, fighters)

    def _swept_geometry(self, slot: int) -> tuple[pygame.FRect, tuple[SweptShape, ...]]:
        """The current tick's flight geometry, read from the dense row."""
        table = self.table
        rect: pygame.FRect = table.column("hitbox")[slot]
        previous_rect: pygame.FRect | None = table.column("previous_rect")[slot]
        shape = table.column("contact_shape")[slot]
        previous_shape = table.column("previous_shape")[slot]
        return swept_box(previous_rect, rect), (SweptShape(previous_shape, shape),)

    def _hit_wall(self, slot: int) -> bool:
        """True when the swept flying box overlaps static collision geometry."""
        swept_rect, shape_sweeps = self._swept_geometry(slot)
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
        self, slot: int, entity_grid: EntityGrid | None, fighters: Sequence[Entity] | None
    ) -> None:
        """Emit the dense row's offensive box into the unified pipeline.

        The pooled sprite is still passed as ``attacker`` because the combat
        protocol reads it; every value the pipeline decides on comes from the
        table. Targets are recorded in the dense set and mirrored onto the
        proxy for the draw path.
        """
        table = self.table
        config = table.column("config")[slot]
        hitbox: pygame.FRect = table.column("hitbox")[slot]
        swept_rect, shape_sweeps = self._swept_geometry(slot)
        proxy: Projectile = table.proxy_of(slot)
        targets: set[str] = table.column("targets_hit")[slot]
        box = OffensiveBox(
            box=hitbox,
            swept=(swept_rect,),
            hit=config.hit,
            swept_shapes=shape_sweeps if config.shape is not ShapeKind.AABB else (),
            faction=table.column("faction")[slot],
            owner_id=table.column("owner_id")[slot],
            can_contact=lambda target_id: target_id not in targets,
            kind="projectile",
            attacker=proxy,
            stop_after_first=not config.pierce,
            record_contact=_record_target(targets, proxy),
        )
        target_list: Any
        if fighters is None:
            movement = self.groups.movement_table
            target_list = (
                tuple(movement.iter_entities())
                if movement is not None
                else self.groups.entity_sprites
            )
        else:
            target_list = fighters
        outcome = self.contact_system.resolve((box,), target_list, entity_grid)  # type: ignore[arg-type]
        self.guard_events.extend(outcome.guard_events)
        self.impact_events.extend(outcome.impact_events)
        if outcome.metrics.contacts and not config.pierce:
            self._release(proxy)

    def _release(self, projectile: Projectile) -> None:
        proxy_id = id(projectile)
        slot = self._slot_of_proxy.pop(proxy_id)
        released = self.table.release(slot)
        self._handle_of_proxy[proxy_id] = (released[0], released[1] + 1)
        projectile.kill()
        self.pool.release(projectile)
