from collections.abc import Iterable, Sequence
from typing import Any

import pygame

from src.combat.shapes import ShapeKind, ShapePose, SweptShape
from src.combat.sweep import swept_box
from src.core.settings import World
from src.physics.platforms import update_moving_platform


class Sprite(pygame.sprite.Sprite):
    one_way: bool = False

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
        self.contact_shape: ShapePose = ShapePose(ShapeKind.AABB, self.rect.size, self.rect.center)
        self._previous_contact_shape: ShapePose | None = None
        self._previous_contact_rect: pygame.FRect | None = None

    def sync_contact_shape(self) -> None:
        self.contact_shape = ShapePose(
            self.contact_shape.kind,
            self.contact_shape.size,
            self.rect.center,
            self.contact_shape.angle,
        )

    def capture_contact_origin(self) -> None:
        self._previous_contact_shape = self.contact_shape
        self._previous_contact_rect = self.rect.copy()

    def swept_contact_rect(self) -> pygame.FRect:
        """Return the contact rectangle swept from the previous tick boundary."""
        return swept_box(self._previous_contact_rect, self.rect)

    def swept_contact_shapes(self) -> tuple[SweptShape, ...]:
        return (SweptShape(self._previous_contact_shape, self.contact_shape),)


class MovingPlatform(Sprite):
    def __init__(
        self,
        pos: tuple[float, float],
        surf: pygame.Surface,
        waypoints: Sequence[tuple[float, float]],
        speed: float,
        groups=None,
        collision_sprites: Iterable[Any] | None = None,
    ):
        super().__init__(pos, color=None, surf=surf, groups=groups)
        self.waypoints = [pygame.math.Vector2(x, y) for (x, y) in waypoints]
        self.speed = speed
        self.current_target = 1
        self.direction = 1
        # Static colliders the platform must not phase through (None keeps
        # the legacy ghost behaviour for synthetic setups and tests).
        self.collision_sprites = collision_sprites
        # Optional grid over those colliders, so the movement check queries
        # its neighbourhood instead of the whole level. None falls back to
        # the full scan.
        self.spatial_hash: Any = None

        self.hitbox: pygame.FRect = self.rect.copy()
        self.old_hitbox: pygame.FRect = self.hitbox.copy()
        self.pos = pygame.math.Vector2(self.rect.topleft)

    def update(self, delta_time: float):
        update_moving_platform(self, delta_time)


class LevelExit(Sprite):
    def __init__(self, pos: tuple[float, float], groups=None):
        surf = pygame.Surface((World.TILE_SIZE, World.TILE_SIZE), pygame.SRCALPHA)
        super().__init__(pos, color=None, surf=surf, groups=groups)
