import math

import pygame

from src.core.sprites import Sprite


class OrbitingHazard(Sprite):
    def __init__(self, pos, surf, radius, start_angle, end_angle, speed, groups=None):
        super().__init__(pos, color=None, surf=surf, groups=groups)
        self.center = pygame.math.Vector2(pos[0], pos[1])
        self.radius = radius
        self.start_angle = math.radians(start_angle)
        self.full_loop = end_angle < 0
        self.end_angle = self.start_angle if self.full_loop else math.radians(end_angle)
        self.speed = speed
        self.angle = self.start_angle
        self.direction = 1
        self._place()

    def _place(self) -> None:
        x = self.center.x + math.cos(self.angle) * self.radius
        y = self.center.y + math.sin(self.angle) * self.radius
        self.rect.center = (x, y)

    def update(self, delta_time: float) -> None:
        if delta_time == 0.0 or self.radius <= 0:
            return
        angular_speed = self.speed / self.radius
        self.angle += angular_speed * delta_time * self.direction
        if self.full_loop:
            self.angle %= 2 * math.pi
        else:
            low, high = min(self.start_angle, self.end_angle), max(self.start_angle, self.end_angle)
            if self.angle > high:
                self.angle, self.direction = high, -1
            elif self.angle < low:
                self.angle, self.direction = low, 1
        self._place()


class SpanHazard(Sprite):
    def __init__(self, pos, surf, speed, flip, groups=None):
        super().__init__(pos, color=None, surf=surf, groups=groups)
        start = pygame.math.Vector2(self.rect.topleft)
        if self.rect.width >= self.rect.height:
            end = start + pygame.math.Vector2(self.rect.width, 0)
        else:
            end = start + pygame.math.Vector2(0, self.rect.height)
        self.point_a = end if flip else start
        self.point_b = start if flip else end
        self.speed = speed
        self.progress = 0.0
        self.direction = 1

    def update(self, delta_time: float) -> None:
        if delta_time == 0.0:
            return
        segment_length = self.point_a.distance_to(self.point_b)
        if segment_length == 0:
            return
        self.progress += (self.speed * delta_time / segment_length) * self.direction
        if self.progress >= 1.0:
            self.progress, self.direction = 1.0, -1
        elif self.progress <= 0.0:
            self.progress, self.direction = 0.0, 1
        self.rect.topleft = self.point_a.lerp(self.point_b, self.progress)