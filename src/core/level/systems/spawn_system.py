"""SpawnSystem: debug-spawn head of the level pipeline (audit F1.2, Phase 3 #2).

Runs first each tick, before the platforms move, so a runtime-spawned enemy
joins the world before any stage reads it.  It owns the debug-spawn
cooldowns and the spawn logic directly (moved here from the former
``DebugController``), so the level no longer drives anything itself.
"""

from typing import TYPE_CHECKING

import pygame

from src.core.settings import Respawn
from src.core.sprite_groups import SpriteGroups
from src.entities.enemies.factory import create_enemy
from src.physics.spatial_hash import SpatialHash

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from src.entities.player import Player

DEBUG_SPAWNS = {
    pygame.K_g: "goblin",
    pygame.K_p: "slime",
    pygame.K_t: "dummy",
}

__all__ = ["DEBUG_SPAWNS", "SpawnSystem"]


class SpawnSystem:
    """Tick the debug spawner (cooldowns decay, key-triggered spawns)."""

    def __init__(self, groups: SpriteGroups, spatial_hash: SpatialHash | None = None) -> None:
        self.groups = groups
        self.spatial_hash = spatial_hash
        self.spawn_cooldowns = dict.fromkeys(DEBUG_SPAWNS.values(), 0.0)

    @property
    def spawn_cooldown_max(self) -> float:
        """Longest remaining debug-spawn cooldown (audit F5.2)."""
        return max(self.spawn_cooldowns.values())

    def process(self, delta_time: float, player: Player) -> None:
        """Decay cooldowns, then spawn enemies for the debug keys held."""
        for enemy_name, cooldown in self.spawn_cooldowns.items():
            if cooldown > 0:
                self.spawn_cooldowns[enemy_name] = cooldown - delta_time

        keys = pygame.key.get_pressed()

        for key, enemy_name in DEBUG_SPAWNS.items():
            if keys[key] and self.spawn_cooldowns[enemy_name] <= 0:
                self._spawn_enemy(enemy_name, player)

    def _spawn_enemy(self, enemy_name: str, player: Player) -> None:
        offset_x = 100 if player.facing_right else -100
        enemy = create_enemy(
            enemy_name,
            pos=(player.hitbox.centerx + offset_x, player.hitbox.top),
            groups=(self.groups.all_sprites,),
            collision_sprites=self.groups.collision_sprites,
            player_reference=player,
        )
        self.groups.combat_sprites.add(enemy)
        self.groups.entity_sprites.add(enemy)
        # Runtime-spawned enemies must join the collision grid too (PERF-01).
        if self.spatial_hash is not None:
            enemy.spatial_hash = self.spatial_hash
        self.spawn_cooldowns[enemy_name] = Respawn.DEBUG_SPAWN_COOLDOWN_S
