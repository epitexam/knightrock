import math
from typing import Any, Iterable

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from src.core.settings import Separation


def hitbox_collide(a: Sprite, b: Sprite) -> bool:
    """Return whether the hitboxes of two sprites overlap."""
    box_a = getattr(a, "hitbox", a.rect)
    box_b = getattr(b, "hitbox", b.rect)
    if isinstance(box_a, (pygame.FRect, pygame.Rect)) and isinstance(
        box_b, (pygame.FRect, pygame.Rect)
    ):
        return box_a.colliderect(box_b)
    return False


def get_nearby_sprites(sprite: Sprite, collision_sprites: Group) -> list[Sprite]:
    """Return the collision sprites near the given sprite."""
    search_area = sprite.hitbox.inflate(
        Separation.SEARCH_INFLATE, Separation.SEARCH_INFLATE
    )

    nearby_sprites: list[Sprite] = []
    for other in collision_sprites:
        box = getattr(other, "hitbox", getattr(other, "rect", None))
        if box is not None and search_area.colliderect(box):
            nearby_sprites.append(other)
    return nearby_sprites


def update_contact_state(entity: Sprite, collision_sprites: Group) -> None:
    """Update floor/left/right contact flags for an entity."""
    height_quarter = entity.hitbox.height / 4
    half_height = entity.hitbox.height / 2

    floor_rect = pygame.FRect(entity.hitbox.bottomleft, (entity.hitbox.width, 2))
    right_rect = pygame.FRect(
        Vector2(entity.hitbox.topright) + Vector2(0, height_quarter),
        (2, half_height),
    )
    left_rect = pygame.FRect(
        Vector2(entity.hitbox.topleft) + Vector2(-2, height_quarter),
        (2, half_height),
    )

    entity.on_surface["floor"] = False
    entity.on_surface["right"] = False
    entity.on_surface["left"] = False

    for sprite in collision_sprites:
        box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
        if box is None:
            continue
        if floor_rect.colliderect(box):
            entity.on_surface["floor"] = True
        if right_rect.colliderect(box):
            entity.on_surface["right"] = True
        if left_rect.colliderect(box):
            entity.on_surface["left"] = True

        if (
            entity.on_surface["floor"]
            and entity.on_surface["right"]
            and entity.on_surface["left"]
        ):
            break

    if entity.on_surface["floor"]:
        entity._on_floor_contact()
    elif entity.on_surface["left"] or entity.on_surface["right"]:
        entity._on_wall_contact()


def resolve_collisions(entity: Sprite, axis: str) -> None:
    """Resolve collisions between an entity and nearby collidable sprites."""
    nearby_sprites = get_nearby_sprites(entity, entity.collision_sprites)
    for sprite in nearby_sprites:
        if sprite is None or not hasattr(sprite, "rect") or sprite.rect is None:
            continue
        if not hitbox_collide(entity, sprite):
            continue

        sprite_old = getattr(sprite, "old_hitbox", getattr(sprite, "old_rect", sprite.rect))
        sprite_box = getattr(sprite, "hitbox", sprite.rect)

        if axis == "horizontal":
            if entity.old_hitbox.right <= sprite_old.left:
                entity.hitbox.right = sprite_box.left
            elif entity.old_hitbox.left >= sprite_old.right:
                entity.hitbox.left = sprite_box.right
            else:
                if abs(entity.hitbox.right - sprite_box.left) < abs(
                    entity.hitbox.left - sprite_box.right
                ):
                    entity.hitbox.right = sprite_box.left
                else:
                    entity.hitbox.left = sprite_box.right
            entity.velocity.x = 0

        elif axis == "vertical":
            if entity.old_hitbox.bottom <= sprite_old.top:
                entity.hitbox.bottom = sprite_box.top
            elif entity.old_hitbox.top >= sprite_old.bottom:
                entity.hitbox.top = sprite_box.bottom
            else:
                if abs(entity.hitbox.bottom - sprite_box.top) < abs(
                    entity.hitbox.top - sprite_box.bottom
                ):
                    entity.hitbox.bottom = sprite_box.top
                else:
                    entity.hitbox.top = sprite_box.bottom
            entity.velocity.y = 0

    entity.sync_rects()
