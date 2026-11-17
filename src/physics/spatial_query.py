"""The broad-phase query port: one shape, two interchangeable implementations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, cast

import pygame

from src.core.settings import Separation
from src.physics.spatial_hash import SpatialHash, collider_box


class QuerySprite(Protocol):
    @property
    def rect(self) -> pygame.Rect | pygame.FRect: ...

    @property
    def hitbox(self) -> pygame.Rect | pygame.FRect: ...


class SpatialQuery(Protocol):
    """Return the colliders near a box, using whatever index is available."""

    def get_nearby(self, box: pygame.FRect) -> list[QuerySprite]: ...


class HashQuery:
    """The O(1) path, backed by a spatial hash."""

    def __init__(self, spatial_hash: SpatialHash) -> None:
        self.spatial_hash = spatial_hash

    def get_nearby(self, box: pygame.FRect) -> list[QuerySprite]:
        return cast(list[QuerySprite], self.spatial_hash.get_nearby(box))


class LinearQuery:
    """The O(n) fallback for callers without an index."""

    def __init__(self, sprites: Iterable[QuerySprite]) -> None:
        self.sprites = sprites

    def get_nearby(self, box: pygame.FRect) -> list[QuerySprite]:
        area = box.inflate(Separation.SEARCH_INFLATE, Separation.SEARCH_INFLATE)
        return [
            other
            for other in self.sprites
            if (candidate := collider_box(other)) is not None and area.colliderect(candidate)
        ]


def make_query(
    spatial_hash: SpatialHash | None, collision_sprites: Iterable[QuerySprite] | None
) -> SpatialQuery:
    """Choose an implementation by what was injected, never by a runtime type check."""
    if spatial_hash is not None:
        return HashQuery(spatial_hash)
    return LinearQuery(collision_sprites if collision_sprites is not None else ())
