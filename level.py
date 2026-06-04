import pygame

from colors import Colors
from player import Player
from settings import *
from sprites import Sprite


class Level:
    def __init__(self, display_surface, tmx_map):
        self.display_surface = display_surface
        self.all_sprites = pygame.sprite.Group()
        self.collision_sprites = pygame.sprite.Group()
        self.setup(tmx_map)

    def setup(self, tmx_map):
        for x, y, surf in tmx_map.get_layer_by_name("Terrain").tiles():
            Sprite((x * TILE_SIZE, y * TILE_SIZE), surf, (self.all_sprites, self.collision_sprites), Colors.blue)

        for obj in tmx_map.get_layer_by_name("Objects"):
            if obj.name == "player":
                Player((obj.x, obj.y), self.all_sprites, self.collision_sprites)

    def run(self, delta_time):
        self.all_sprites.update(delta_time)
        self.display_surface.fill(Colors.red)
        self.all_sprites.draw(self.display_surface)