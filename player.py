import pygame
from pygame.math import Vector2

from colors import Colors
from settings import *
from sprites import Sprite


class Player(pygame.sprite.Sprite):
    def __init__(self, pos, groups) -> None:
        super().__init__(groups)
        self.image = pygame.Surface((48, 56))
        self.image.fill(Colors.green)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.direction = Vector2(1, 0)
        self.speed = SPEED

    def input(self):
        keys = pygame.key.get_pressed()
        input_vector = Vector2(0, 0)

        if keys[pygame.K_RIGHT]:
            if self.rect.x <= WINDOW_WIDTH:
                input_vector.x += 1

        if keys[pygame.K_LEFT]:
            if self.rect.x > 0:
                input_vector.x += -1

        self.direction = input_vector.normalize() if input_vector else input_vector

    def move(self, delta_time):
        self.rect.topleft += self.direction * self.speed * delta_time

    def update(self, delta_time):
        self.input()
        self.move(delta_time)
