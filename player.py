import pygame
from pygame.math import Vector2

from colors import Colors
from settings import *
from sprites import Sprite


class Player(pygame.sprite.Sprite):
    def __init__(self, pos, groups, collision_sprites) -> None:
        super().__init__(groups)
        self.image = pygame.Surface((48, 56))
        self.image.fill(Colors.green)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.direction = Vector2(1, 0)
        self.speed = SPEED
        self.collision_sprites = collision_sprites
        self.old_rect = self.rect.copy()
        self.gravity = GRAVITY

    def input(self):
        keys = pygame.key.get_pressed()
        input_vector = Vector2(0, 0)

        if keys[pygame.K_RIGHT]:
            if self.rect.x <= WINDOW_WIDTH:
                input_vector.x += 1

        if keys[pygame.K_LEFT]:
            if self.rect.x > 0:
                input_vector.x += -1

        self.direction.x = input_vector.normalize().x if input_vector else input_vector.x

    def move(self, delta_time):

        self.rect.x += self.direction.x * self.speed * delta_time
        self.collision('horizontal')

        self.direction.y += self.gravity / 2 * delta_time
        self.rect.y += self.direction.y * delta_time
        self.direction.y += self.gravity / 2 * delta_time
        self.collision('vertical')

    def collision(self, axis):
        for sprite in self.collision_sprites:
            if sprite.rect.colliderect(self.rect):
                if axis == "horizontal":
                    if self.rect.left <= sprite.rect.right and self.old_rect.left >= sprite.old_rect.right: 
                        self.rect.left = sprite.rect.right
                    elif self.rect.right >= sprite.rect.left and self.old_rect.right <= sprite.old_rect.left:
                        self.rect.right = sprite.rect.left
                else:  # vertical
                    if self.rect.top <= sprite.rect.bottom and self.old_rect.top >= sprite.old_rect.bottom:
                        self.rect.top = sprite.rect.bottom
                    elif self.rect.bottom >= sprite.rect.top and self.old_rect.bottom <= sprite.old_rect.top:
                        self.rect.bottom = sprite.rect.top
                    self.direction.y = 0


    def update(self, delta_time):
        self.old_rect = self.rect.copy()
        self.input()
        self.move(delta_time)

