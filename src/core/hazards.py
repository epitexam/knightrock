import math
from collections.abc import Mapping
from typing import Protocol

import pygame

from src.core.animation.animator import AnimationSpec, Animator
from src.core.asset_library import shared_library
from src.core.sprites import Sprite
from src.physics.hazard_damage import HazardDamageSystem


class AnimatedSprite(Protocol):
    """Minimal surface a sprite must expose to be animation-tickable."""

    animator: Animator | None
    rect: pygame.FRect
    image: pygame.Surface


def build_hazard_animator(animations: Mapping[str, str], default: str) -> Animator:
    """Create an Animator for hazard sprite sheets (Phase 2 #1)."""
    specs = {
        name: AnimationSpec(name, directory, frame_duration=0.12, loop=True)
        for name, directory in animations.items()
    }
    return Animator(shared_library(), specs, default=default)


def _tick_animation(sprite: AnimatedSprite, delta_time: float, facing_right: bool = True) -> None:
    """Advance a sprite's optional animator and publish its surface."""
    animator = sprite.animator
    if animator is None:
        return
    animator.update(delta_time)
    surface = animator.surface((round(sprite.rect.width), round(sprite.rect.height)), facing_right)
    if surface is not None:
        sprite.image = surface


class OrbitingHazard(Sprite):
    def __init__(
        self,
        pos,
        surf,
        radius,
        start_angle,
        end_angle,
        speed,
        groups=None,
        damage: float = HazardDamageSystem.DEFAULT_DAMAGE,
        animator: Animator | None = None,
    ):
        super().__init__(pos, color=None, surf=surf, groups=groups)
        self.animator = animator
        self.center = pygame.math.Vector2(pos[0], pos[1])
        self.radius = radius
        self.start_angle = math.radians(start_angle)
        self.full_loop = end_angle < 0
        self.end_angle = self.start_angle if self.full_loop else math.radians(end_angle)
        self.speed = speed
        self.damage = damage
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
        _tick_animation(self, delta_time)


class SpanHazard(Sprite):
    def __init__(
        self,
        pos,
        surf,
        speed,
        flip,
        groups=None,
        damage: float = HazardDamageSystem.DEFAULT_DAMAGE,
        animator: Animator | None = None,
    ):
        super().__init__(pos, color=None, surf=surf, groups=groups)
        self.animator = animator
        start = pygame.math.Vector2(self.rect.topleft)
        if self.rect.width >= self.rect.height:
            end = start + pygame.math.Vector2(self.rect.width, 0)
        else:
            end = start + pygame.math.Vector2(0, self.rect.height)
        self.point_a = end if flip else start
        self.point_b = start if flip else end
        self.speed = speed
        self.damage = damage
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
        _tick_animation(self, delta_time)
