"""ProjectileSystem: pooled flying hitboxes (audit Phase 5 #3).

Extracted as a world stage like the other ``core/level/systems`` stages. The
per-tick :class:`~src.physics.entity_grid.EntityGrid` (rebuilt by
``GameplayLoop``) prunes target candidates around each projectile box
(O(n . k) instead of projectiles x entities); without a grid the pairs are
tested exhaustively. Damage goes through
:class:`~src.combat.hit_resolver.HitResolver` so ranged hits share armor,
stagger and finisher rules with melee.
"""

from __future__ import annotations

import pygame

from src.combat.hit_resolver import HitResolver
from src.core.object_pool import ObjectPool
from src.core.sprite_groups import SpriteGroups
from src.entities.projectile import Projectile, ProjectileConfig
from src.physics.entity_grid import EntityGrid
from src.physics.spatial_hash import SpatialHash

__all__ = ["ProjectileSystem"]


def _reset_projectile(projectile: Projectile) -> None:
    projectile.reset()


class ProjectileSystem:
    """Spawn, integrate and resolve pooled projectiles once per tick."""

    def __init__(
        self,
        groups: SpriteGroups,
        pool: ObjectPool[Projectile] | None = None,
        spatial_hash: SpatialHash | None = None,
    ) -> None:
        self.groups = groups
        self.pool: ObjectPool[Projectile] = (
            pool if pool is not None else ObjectPool(Projectile, reset=_reset_projectile)
        )
        self.spatial_hash = spatial_hash

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
        targets = self._candidates(projectile, entity_grid)
        for target in targets:
            if getattr(target, "is_dead", False):
                continue
            if getattr(target, "faction", None) == projectile.faction:
                continue
            target_id = getattr(target, "id", None)
            if target_id is None or not projectile.can_contact(target_id):
                continue
            hurtbox = getattr(target, "hurtbox", None)
            if hurtbox is None:
                continue
            if not projectile.hitbox.colliderect(hurtbox):
                continue
            result = HitResolver.resolve(
                attacker=projectile,  # type: ignore[arg-type]
                target=target,
                hit=projectile.config.hit,
            )
            if not (result.applied or result.blocked):
                continue
            projectile.targets_hit.add(target_id)
            if not projectile.config.pierce:
                self._release(projectile)
                return

    def _candidates(
        self,
        projectile: Projectile,
        entity_grid: EntityGrid | None,
    ) -> list:
        entities = list(self.groups.entity_sprites)
        if entity_grid is None:
            return entities
        by_id = {id(entity): entity for entity in entities}
        candidates: list = []
        seen: set[int] = set()
        for member in entity_grid.near(projectile.hitbox):
            key = id(member)
            if key in seen or key not in by_id:
                continue
            seen.add(key)
            candidates.append(by_id[key])
        # Group order keeps hit resolution deterministic like CombatSystem.
        order = {id(entity): index for index, entity in enumerate(entities)}
        candidates.sort(key=lambda entity: order[id(entity)])
        return candidates

    def _release(self, projectile: Projectile) -> None:
        projectile.kill()
        self.pool.release(projectile)
