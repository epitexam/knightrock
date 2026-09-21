"""ProjectileSystem: pooled flying hitboxes (audit Phase 5 #3).

Extracted as a world stage like the other ``core/level/systems`` stages.
Targets are resolved through the unified
:class:`~src.core.level.systems.contact_system.ContactSystem` (P4.1), which
owns the per-tick grid prune (O(n . k) instead of projectiles x entities;
exhaustive without a grid) and the shared hit resolution: ranged hits go
through :class:`~src.combat.hit_resolver.HitResolver` so they share armor,
stagger and finisher rules with melee.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from src.combat.combatant_protocol import Combatant
from src.core.level.systems.contact_system import ContactSystem, GuardEvent, OffensiveBox
from src.core.object_pool import ObjectPool
from src.core.sprite_groups import SpriteGroups
from src.entities.projectile import Projectile, ProjectileConfig
from src.physics.entity_grid import EntityGrid
from src.physics.spatial_hash import SpatialHash

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
    ) -> None:
        self.groups = groups
        self.pool: ObjectPool[Projectile] = (
            pool if pool is not None else ObjectPool(Projectile, reset=_reset_projectile)
        )
        self.spatial_hash = spatial_hash
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )
        self.guard_events: list[GuardEvent] = []

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
        return projectile

    def process(
        self,
        delta_time: float,
        entity_grid: EntityGrid | None = None,
    ) -> None:
        """Advance every projectile and resolve contacts."""
        self.guard_events.clear()
        if delta_time <= 0.0:
            return
        for projectile in list(self.groups.projectile_sprites):
            if not isinstance(projectile, Projectile):
                continue
            projectile.update(delta_time)
            if projectile.is_dead:
                self._release(projectile)
                continue
            if self._hit_wall(projectile):
                self._release(projectile)
                continue
            self._resolve_contacts(projectile, entity_grid)

    def _hit_wall(self, projectile: Projectile) -> bool:
        """True when the flying box truly overlaps static collision geometry."""
        if self.spatial_hash is not None:
            for sprite in self.spatial_hash.get_nearby(projectile.hitbox):
                box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
                if box is not None and pygame.FRect(box).colliderect(projectile.hitbox):
                    return True
            return False
        for sprite in self.groups.collision_sprites:
            box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
            if box is not None and pygame.FRect(box).colliderect(projectile.hitbox):
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
            swept=(projectile.hitbox,),
            hit=config.hit,
            faction=projectile.faction,
            owner_id=projectile.id,
            can_contact=projectile.can_contact,
            kind="projectile",
            attacker=projectile,
            stop_after_first=not config.pierce,
            record_contact=_record_target(projectile),
        )
        outcome = self.contact_system.resolve(
            (box,), self.groups.entity_sprites, entity_grid
        )
        self.guard_events.extend(outcome.guard_events)
        if outcome.metrics.contacts and not config.pierce:
            self._release(projectile)

    def _release(self, projectile: Projectile) -> None:
        projectile.kill()
        self.pool.release(projectile)
