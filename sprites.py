from typing import Iterable, Optional, Tuple, Union

import pygame

from settings import World


class Sprite(pygame.sprite.Sprite):
    def __init__(
        self,
        pos: Tuple[int, int],
        color: Optional[Tuple[int, int, int]] = None,
        surf: pygame.Surface = pygame.Surface((World.TILE_SIZE, World.TILE_SIZE)),
        groups: Union[
            pygame.sprite.AbstractGroup, Iterable[pygame.sprite.AbstractGroup], None
        ] = None,
    ) -> None:
        super().__init__()

        if groups is not None:
            if isinstance(groups, pygame.sprite.AbstractGroup):
                groups.add(self)
            else:
                for group in groups:
                    group.add(self)

        self.image: pygame.Surface = surf
        if color is not None:
            self.image.fill(color)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.old_rect: pygame.FRect = self.rect.copy()


class MovingPlatform(Sprite):
    def __init__(
        self,
        pos: Tuple[int, int],
        surf: pygame.Surface,
        waypoints: list[Tuple[int, int]],
        speed: float,
        groups=None,
    ):
        super().__init__(pos, color=None, surf=surf, groups=groups)
        self.waypoints = [pygame.math.Vector2(x, y) for (x, y) in waypoints]
        self.speed = speed
        self.current_target = 1
        self.direction = 1
        self.old_rect = self.rect.copy()

        self.hitbox: pygame.FRect = self.rect.copy()
        self.old_hitbox: pygame.FRect = self.hitbox.copy()

    def update(self, delta_time: float):

        self.old_rect = self.rect.copy()
        self.old_hitbox = self.hitbox.copy()

        if not self.waypoints:
            return

        target = self.waypoints[self.current_target]
        pos = pygame.math.Vector2(self.rect.topleft)
        direction = target - pos
        distance = direction.length()

        if distance < 1.0:
            self.rect.topleft = target
            self.current_target += self.direction
            if self.current_target in (len(self.waypoints), -1):
                self.direction *= -1
                self.current_target += self.direction
        else:
            direction.normalize_ip()
            self.rect.topleft += direction * self.speed * delta_time

        self.hitbox.topleft = self.rect.topleft
        self.hitbox.width = self.rect.width
        self.hitbox.height = self.rect.height
