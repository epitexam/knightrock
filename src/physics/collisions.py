from collections.abc import Iterable
from typing import Literal, Protocol

import pygame
from pygame.math import Vector2

from src.core.settings import Separation
from src.physics.spatial_hash import SpatialHash, SpatialHashable


class CollisionSprite(Protocol):
    @property
    def rect(self) -> pygame.Rect | pygame.FRect: ...

    @property
    def hitbox(self) -> pygame.Rect | pygame.FRect: ...


class CollisionEntity(Protocol):
    rect: pygame.FRect
    hitbox: pygame.FRect
    old_hitbox: pygame.FRect
    velocity: Vector2
    on_surface: dict[str, bool]
    collision_sprites: Iterable[CollisionSprite]

    def sync_rects(self) -> None: ...

    def _on_floor_contact(self) -> None: ...

    def _on_wall_contact(self) -> None: ...


def hitbox_collide(a: CollisionSprite, b: CollisionSprite) -> bool:
    """Return whether the hitboxes of two sprites overlap."""
    box_a = getattr(a, "hitbox", a.rect)
    box_b = getattr(b, "hitbox", b.rect)
    if isinstance(box_a, (pygame.FRect, pygame.Rect)) and isinstance(
        box_b, (pygame.FRect, pygame.Rect)
    ):
        return box_a.colliderect(box_b)
    return False


def get_nearby_sprites(
    sprite: CollisionEntity,
    spatial_hash: SpatialHash | None = None,
    collision_sprites: Iterable[CollisionSprite] | None = None,
) -> list[CollisionSprite]:
    """Return the collision sprites near the given sprite.
    
    Uses spatial hash for O(1) lookup when available, otherwise falls back
    to the original O(n) search (PERF-01).
    """
    if spatial_hash is not None:
        # Use spatial hash for O(1) lookup
        return spatial_hash.get_nearby(sprite.hitbox)
    
    # Fallback to original O(n) search for backward compatibility
    if collision_sprites is None:
        return []
    search_area = sprite.hitbox.inflate(
        Separation.SEARCH_INFLATE, Separation.SEARCH_INFLATE)
    return [
        other for other in collision_sprites
        if (box := getattr(other, "hitbox", getattr(other, "rect", None))) is not None
        and search_area.colliderect(box)
    ]


def update_contact_state(
    entity: CollisionEntity,
    collision_sprites: Iterable[CollisionSprite],
) -> None:
    """Update floor/left/right contact flags for an entity."""
    hq = entity.hitbox.height / 4
    hh = entity.hitbox.height / 2

    floor_rect = pygame.FRect(entity.hitbox.bottomleft,
                              (entity.hitbox.width, 2))
    right_rect = pygame.FRect(
        Vector2(entity.hitbox.topright) + Vector2(0, hq), (2, hh))
    left_rect = pygame.FRect(
        Vector2(entity.hitbox.topleft) + Vector2(-2, hq), (2, hh))

    on = entity.on_surface
    on["floor"] = on["right"] = on["left"] = False

    for sprite in collision_sprites:
        box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
        if box is None:
            continue
        if floor_rect.colliderect(box):
            on["floor"] = True
        if right_rect.colliderect(box):
            on["right"] = True
        if left_rect.colliderect(box):
            on["left"] = True
        if on["floor"] and on["right"] and on["left"]:
            break

    if on["floor"]:
        entity._on_floor_contact()
    elif on["left"] or on["right"]:
        entity._on_wall_contact()


def resolve_collisions(
    entity: CollisionEntity,
    axis: Literal["horizontal", "vertical"],
    nearby_sprites: list[CollisionSprite] | None = None,
) -> None:
    """Resolve collisions between an entity and nearby collidable sprites."""
    if nearby_sprites is None:
        nearby_sprites = get_nearby_sprites(entity, entity.collision_sprites)

    for sprite in nearby_sprites:
        if not hasattr(sprite, "rect") or sprite.rect is None:
            continue
        if not hitbox_collide(entity, sprite):
            continue

        sprite_old = getattr(sprite, "old_hitbox", getattr(
            sprite, "old_rect", sprite.rect))
        sprite_box = getattr(sprite, "hitbox", sprite.rect)

        if axis == "horizontal":
            if entity.hitbox.bottom <= sprite_box.top + 4:
                continue

        was_overlapping = entity.old_hitbox.colliderect(sprite_old)

        if axis == "horizontal":
            if not was_overlapping and entity.old_hitbox.right <= sprite_old.left:
                entity.hitbox.right = sprite_box.left
            elif not was_overlapping and entity.old_hitbox.left >= sprite_old.right:
                entity.hitbox.left = sprite_box.right
            elif abs(entity.hitbox.right - sprite_box.left) < abs(entity.hitbox.left - sprite_box.right):
                entity.hitbox.right = sprite_box.left
            else:
                entity.hitbox.left = sprite_box.right
            entity.velocity.x = 0
        else:
            if not was_overlapping and entity.old_hitbox.bottom <= sprite_old.top:
                entity.hitbox.bottom = sprite_box.top
            elif not was_overlapping and entity.old_hitbox.top >= sprite_old.bottom:
                entity.hitbox.top = sprite_box.bottom
            elif abs(entity.hitbox.bottom - sprite_box.top) < abs(entity.hitbox.top - sprite_box.bottom):
                entity.hitbox.bottom = sprite_box.top
            else:
                entity.hitbox.top = sprite_box.bottom
            entity.velocity.y = 0

    entity.sync_rects()
