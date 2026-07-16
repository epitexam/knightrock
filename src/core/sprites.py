from typing import Iterable, Optional, Tuple, Union

import pygame

from src.core.settings import World
from src.physics.platforms import update_moving_platform


class Sprite(pygame.sprite.Sprite):
    """Represent a base game sprite with floating-point rect precision."""

    def __init__(
        self,
        pos: Tuple[int, int],
        color: Optional[Tuple[int, int, int]] = None,
        surf: Optional[pygame.Surface] = None,
        groups: Union[
            pygame.sprite.AbstractGroup, Iterable[pygame.sprite.AbstractGroup], None
        ] = None,
    ) -> None:
        """Initialize the Sprite instance and assign it to specified groups."""
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
    """Represent a platform that moves between predefined waypoints."""

    def __init__(
        self,
        pos: Tuple[int, int],
        surf: pygame.Surface,
        waypoints: list[Tuple[int, int]],
        speed: float,
        groups=None,
    ):
        """Initialize the MovingPlatform with waypoints, speed, and physics properties."""
        super().__init__(pos, color=None, surf=surf, groups=groups)
        self.waypoints = [pygame.math.Vector2(x, y) for (x, y) in waypoints]
        self.speed = speed
        self.current_target = 1
        self.direction = 1

        self.hitbox: pygame.FRect = self.rect.copy()
        self.old_hitbox: pygame.FRect = self.hitbox.copy()
        self.pos = pygame.math.Vector2(self.rect.topleft)

    def update(self, delta_time: float):
        """Update the platform position based on its movement logic."""
        update_moving_platform(self, delta_time)