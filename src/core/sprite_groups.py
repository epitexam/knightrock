from dataclasses import dataclass, field

import pygame


@dataclass
class SpriteGroups:
    all_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    collision_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    moving_platforms: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    combat_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    entity_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    fx_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    hazard_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    fg_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    exit_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)