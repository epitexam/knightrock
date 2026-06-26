import pygame
from src.entities.enemy import Goblin


class DebugController:
    def __init__(self, all_sprites, collision_sprites, combat_sprites, entity_sprites):
        self.all_sprites = all_sprites
        self.collision_sprites = collision_sprites
        self.combat_sprites = combat_sprites
        self.entity_sprites = entity_sprites
        self.spawn_cooldown = 0.0

    def update(self, delta_time, player):
        if self.spawn_cooldown > 0:
            self.spawn_cooldown -= delta_time

        keys = pygame.key.get_pressed()
        if keys[pygame.K_g] and self.spawn_cooldown <= 0 and player is not None:
            offset_x = 100 if player.facing_right else -100
            goblin = Goblin(
                pos=(player.hitbox.centerx + offset_x, player.hitbox.top),
                groups=(self.all_sprites,),
                collision_sprites=self.collision_sprites,
                player_reference=player,
            )
            self.combat_sprites.add(goblin)
            self.entity_sprites.add(goblin)
            self.spawn_cooldown = 0.5