from collections.abc import Iterable, Sequence

import pygame

from src.core.settings import World
from src.physics.platforms import update_moving_platform


class Sprite(pygame.sprite.Sprite):
    def __init__(
        self,
        pos: tuple[float, float],
        color: tuple[int, int, int] | None = None,
        surf: pygame.Surface | None = None,
        groups: pygame.sprite.AbstractGroup | Iterable[pygame.sprite.AbstractGroup] | None = None,
    ) -> None:
        super().__init__()

        if groups is not None:
            if isinstance(groups, pygame.sprite.AbstractGroup):
                groups.add(self)
            else:
                for group in groups:
                    group.add(self)

        if surf is None:
            surf = pygame.Surface((World.TILE_SIZE, World.TILE_SIZE))
        self.image: pygame.Surface = surf
        if color is not None:
            self.image.fill(color)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.old_rect: pygame.FRect = self.rect.copy()


class MovingPlatform(Sprite):
    def __init__(
        self,
        pos: tuple[float, float],
        surf: pygame.Surface,
        waypoints: Sequence[tuple[float, float]],
        speed: float,
        groups=None,
    ):
        super().__init__(pos, color=None, surf=surf, groups=groups)
        self.waypoints = [pygame.math.Vector2(x, y) for (x, y) in waypoints]
        self.speed = speed
        self.current_target = 1
        self.direction = 1

        self.hitbox: pygame.FRect = self.rect.copy()
        self.old_hitbox: pygame.FRect = self.hitbox.copy()
        self.pos = pygame.math.Vector2(self.rect.topleft)

    def update(self, delta_time: float):
        update_moving_platform(self, delta_time)


class LevelExit(Sprite):
    def __init__(self, pos: tuple[float, float], groups=None):
        surf = pygame.Surface((World.TILE_SIZE, World.TILE_SIZE), pygame.SRCALPHA)
        super().__init__(pos, color=None, surf=surf, groups=groups)