import pygame

from src.entities.enemies.factory import create_enemy
from src.core.sprite_groups import SpriteGroups
from src.physics.spatial_hash import SpatialHash


DEBUG_SPAWNS = {
    pygame.K_g: "goblin",
    pygame.K_p: "slime",
    pygame.K_t: "dummy",
}


class DebugController:
    def __init__(self, groups: SpriteGroups, spatial_hash: SpatialHash | None = None):
        self.groups = groups
        self.spatial_hash = spatial_hash
        self.spawn_cooldowns = {enemy_name: 0.0 for enemy_name in DEBUG_SPAWNS.values()}

    @property
    def spawn_cooldown(self):
        return max(self.spawn_cooldowns.values())

    def update(self, delta_time, player):
        for enemy_name, cooldown in self.spawn_cooldowns.items():
            if cooldown > 0:
                self.spawn_cooldowns[enemy_name] = cooldown - delta_time

        keys = pygame.key.get_pressed()

        for key, enemy_name in DEBUG_SPAWNS.items():
            if keys[key] and self.spawn_cooldowns[enemy_name] <= 0:
                self._spawn_enemy(enemy_name, player)

    def _spawn_enemy(self, enemy_name, player):
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
        self.spawn_cooldowns[enemy_name] = 0.5