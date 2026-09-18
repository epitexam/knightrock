"""Flying offensive hitbox (audit Phase 5 #3).

A projectile is a pooled sprite with its own ``hitbox`` (the offensive box),
``hurtbox`` (so it can be intercepted later), ``faction`` and lifetime. It
reuses :class:`~src.combat.hit_resolver.HitResolver` for damage so melee and
ranged hits share armor, stagger and finisher rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any

import pygame
from pygame.math import Vector2
from pygame.sprite import Sprite

from src.combat.damage_types import DamageType
from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig

_PROJECTILE_ID_SEQUENCE = count()

__all__ = ["FIREBOLT_CONFIG", "PIERCING_BOLT_CONFIG", "Projectile", "ProjectileConfig"]


@dataclass(frozen=True)
class ProjectileConfig:
    """Immutable projectile tuning (data-driven ready)."""

    size: tuple[float, float] = (12.0, 12.0)
    lifetime: float = 2.0
    hit: HitProperties = field(
        default_factory=lambda: HitProperties(damage=5.0),
    )
    pierce: bool = False


class Projectile(Sprite):
    """Pooled flying hitbox. Recycled through ``ObjectPool``, never rebuilt.

    Expose un ``combat`` neutre (RF-1) : le projectile ne fait que porter
    un coup, il satisfait ``AttackerPort`` (hitbox + suivi combo no-op)
    sans santé ni réactions.
    """

    def __init__(self) -> None:
        super().__init__()
        self.id: str = f"p{next(_PROJECTILE_ID_SEQUENCE)}"
        self.image = pygame.Surface((8, 8))
        self.image.fill((255, 200, 60))
        self.rect = self.image.get_rect()
        self.hitbox = pygame.FRect(0, 0, 8, 8)
        self.velocity = Vector2(0, 0)
        self.faction: str = "neutral"
        self.config: ProjectileConfig = ProjectileConfig()
        self.life: float = 0.0
        self.active: bool = False
        self.is_dead: bool = True
        self.targets_hit: set[str] = set()
        self.facing_right: bool = True
        from src.combat.combat_component import NullCombatComponent

        self.combat = NullCombatComponent()

    @property
    def hurtbox(self) -> pygame.FRect:
        """Body box used if something intercepts the projectile itself."""
        return self.hitbox

    def launch(
        self,
        config: ProjectileConfig,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        faction: str,
    ) -> None:
        """Arm a pooled instance for flight."""
        self.config = config
        self.hitbox = pygame.FRect(pos[0], pos[1], config.size[0], config.size[1])
        self.velocity = Vector2(velocity)
        self.faction = faction
        self.facing_right = self.velocity.x >= 0
        self.life = config.lifetime
        self.active = True
        self.is_dead = False
        self.targets_hit.clear()
        self.image = pygame.Surface((int(config.size[0]), int(config.size[1])))
        self.image.fill((255, 200, 60))
        self.rect = pygame.Rect(int(pos[0]), int(pos[1]), int(config.size[0]), int(config.size[1]))
        self.sync_rects()

    def reset(self) -> None:
        """Park the instance back to an inert state (pool ``reset`` hook)."""
        self.active = False
        self.is_dead = True
        self.life = 0.0
        self.velocity.update(0, 0)
        self.targets_hit.clear()

    def sync_rects(self) -> None:
        """Keep the integer ``rect`` (render/cull) on the float ``hitbox``."""
        assert self.rect is not None
        self.rect.topleft = (int(self.hitbox.x), int(self.hitbox.y))

    def update(self, delta_time: float) -> None:
        """Integrate flight and age; expire without freeing (system frees)."""
        if not self.active or self.is_dead:
            return
        self.hitbox.x += self.velocity.x * delta_time
        self.hitbox.y += self.velocity.y * delta_time
        self.life -= delta_time
        if self.life <= 0.0:
            self.is_dead = True
            self.active = False
        self.sync_rects()

    def can_contact(self, target_id: str) -> bool:
        """One shared contact per target (no double damage, even on pierce)."""
        return target_id not in self.targets_hit

    def save_state(self) -> dict[str, Any]:
        """Minimal snapshot for tests/debug (not part of rollback yet)."""
        return {
            "id": self.id,
            "pos": (self.hitbox.x, self.hitbox.y),
            "velocity": (self.velocity.x, self.velocity.y),
            "life": self.life,
            "active": self.active,
        }


#: Straight firebolt for debug key V (Phase 5 #3 showcase).
FIREBOLT_CONFIG = ProjectileConfig(
    size=(12.0, 12.0),
    lifetime=2.0,
    hit=HitProperties(
        damage=10,
        knockback=KnockbackConfig(power=(250.0, -100.0)),
        damage_type=DamageType.PIERCE,
        stagger=0.15,
    ),
    pierce=False,
)

#: Piercing bolt for debug key B (Phase 5 #3 showcase).
PIERCING_BOLT_CONFIG = ProjectileConfig(
    size=(14.0, 14.0),
    lifetime=2.5,
    hit=HitProperties(
        damage=8,
        knockback=KnockbackConfig(power=(200.0, -80.0)),
        damage_type=DamageType.PIERCE,
        stagger=0.1,
    ),
    pierce=True,
)
