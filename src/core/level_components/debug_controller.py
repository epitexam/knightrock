import pygame
from src.entities.enemies.factory import create_enemy


DEBUG_SPAWNS = {
    pygame.K_g: "goblin",
    pygame.K_p: "slime",
    pygame.K_t: "dummy",
}


class DebugController:
    """Manage debug tools and on-screen debug state."""
    def __init__(self, all_sprites, collision_sprites, combat_sprites, entity_sprites):
        """Initialize the DebugController instance."""
        self.all_sprites = all_sprites
        self.collision_sprites = collision_sprites
        self.combat_sprites = combat_sprites
        self.entity_sprites = entity_sprites
        self.spawn_cooldowns = {
            enemy_name: 0.0 for enemy_name in DEBUG_SPAWNS.values()
        }

    @property
    def spawn_cooldown(self):
        """Return the current global spawn cooldown (max of both)."""
        return max(self.spawn_cooldowns.values())

    def update(self, delta_time, player):
        """Update the current state."""
        for enemy_name, cooldown in self.spawn_cooldowns.items():
            if cooldown > 0:
                self.spawn_cooldowns[enemy_name] = cooldown - delta_time

        keys = pygame.key.get_pressed()
        if player is None:
            return

        for key, enemy_name in DEBUG_SPAWNS.items():
            if keys[key] and self.spawn_cooldowns[enemy_name] <= 0:
                self._spawn_enemy(enemy_name, player)

    def _spawn_enemy(self, enemy_name, player):
        """Spawn an enemy near the player for debug purposes."""
        offset_x = 100 if player.facing_right else -100
        enemy = create_enemy(
            enemy_name,
            pos=(player.hitbox.centerx + offset_x, player.hitbox.top),
            groups=(self.all_sprites,),
            collision_sprites=self.collision_sprites,
            player_reference=player,
        )
        self.combat_sprites.add(enemy)
        self.entity_sprites.add(enemy)
        self.spawn_cooldowns[enemy_name] = 0.5
