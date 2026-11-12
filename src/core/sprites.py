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

    #: The part of the image that touches, in image coordinates, or ``None``
    #: for the whole image. A hazard's art rarely fills its rectangle -- floor
    #: spikes use the bottom half of theirs -- and a contact tested against the
    #: full rectangle hurts the player before anything visible reaches him.
    contact_area: pygame.FRect | None = None

    def contact_rect(self) -> pygame.FRect:
        """Where this sprite touches, in world coordinates."""
        area = self.contact_area
        if area is None:
            return self.rect.copy()
        return pygame.FRect(self.rect.x + area.x, self.rect.y + area.y, area.w, area.h)

    def fit_contact(self, area: pygame.FRect, round_shape: bool = False) -> None:
        """Touch only through ``area`` of the image; as a circle in it when ``round_shape``.

        The circle is the largest one centred in the area, for art that is a
        disc in a square frame (a saw, a spiked ball): its corners are empty,
        and a square contact would hurt from them.
        """
        self.contact_area = pygame.FRect(area)
        if round_shape:
            diameter = min(area.w, area.h)
            self.contact_shape = ShapePose(ShapeKind.CIRCLE, (diameter, diameter))
        else:
            self.contact_shape = ShapePose(ShapeKind.AABB, (area.w, area.h))
        self.sync_contact_shape()

    def sync_contact_shape(self) -> None:
        self.contact_shape = ShapePose(
            self.contact_shape.kind,
            self.contact_shape.size,
            self.contact_rect().center,
            self.contact_shape.angle,
        )

    def capture_contact_origin(self) -> None:
        self._previous_contact_shape = self.contact_shape
        self._previous_contact_rect = self.contact_rect()

    def swept_contact_rect(self) -> pygame.FRect:
        """Return the contact rectangle swept from the previous tick boundary."""
        return swept_box(self._previous_contact_rect, self.contact_rect())

    def swept_contact_shapes(self) -> tuple[SweptShape, ...]:
        return (SweptShape(self._previous_contact_shape, self.contact_shape),)


class MovingPlatform(Sprite):
    def __init__(
        self,
        pos: tuple[float, float],
        surf: pygame.Surface,
        waypoints: Sequence[tuple[float, float]],
        speed: float,
        groups: pygame.sprite.AbstractGroup | Iterable[pygame.sprite.AbstractGroup] | None = None,
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

    def update(self, delta_time: float) -> None:
        update_moving_platform(self, delta_time)


class LevelExit(Sprite):
    def __init__(
        self,
        pos: tuple[float, float],
        groups: pygame.sprite.AbstractGroup | None = None,
        size: tuple[float, float] | None = None,
    ) -> None:
        # The object's own rectangle, so the trigger is as tall and wide as the
        # flag drawn in Tiled. An object placed without a size falls back to a
        # tile, which is what a bare point marker in Tiled means anyway.
        width, height = size if size else (World.TILE_SIZE, World.TILE_SIZE)
        surf = pygame.Surface((max(width, 1.0), max(height, 1.0)), pygame.SRCALPHA)
        super().__init__(pos, color=None, surf=surf, groups=groups)
