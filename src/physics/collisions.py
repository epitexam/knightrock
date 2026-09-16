from collections.abc import Iterable
from typing import Literal, Protocol, cast

import pygame
from pygame.math import Vector2

from src.core.settings import Collision, GameFeel, Separation
from src.physics.spatial_hash import SpatialHash


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


def _shift_is_free(
    entity: CollisionEntity,
    shifted: pygame.FRect,
    nearby_sprites: Iterable[CollisionSprite],
    ignore: CollisionSprite | None = None,
) -> bool:
    """Whether ``shifted`` overlaps no nearby collider (except ``ignore``)."""
    for other in nearby_sprites:
        if other is ignore:
            continue
        box = getattr(other, "hitbox", getattr(other, "rect", None))
        if box is not None and shifted.colliderect(box):
            return False
    return True


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
    # Only use spatial_hash if it's actually a SpatialHash instance
    if isinstance(spatial_hash, SpatialHash):
        # The grid stores heterogeneous members (rect-only tiles as well as
        # hitbox-bearing sprites); every consumer re-derives the box with
        # getattr, so narrowing the member type back to CollisionSprite is
        # safe here.
        return cast(list[CollisionSprite], spatial_hash.get_nearby(sprite.hitbox))

    # Fallback to original O(n) search for backward compatibility
    if collision_sprites is None:
        return []
    search_area = sprite.hitbox.inflate(Separation.SEARCH_INFLATE, Separation.SEARCH_INFLATE)
    return [
        other
        for other in collision_sprites
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

    floor_rect = pygame.FRect(
        entity.hitbox.bottomleft, (entity.hitbox.width, Collision.PROBE_THICKNESS_PX)
    )
    right_rect = pygame.FRect(
        Vector2(entity.hitbox.topright) + Vector2(0, hq),
        (Collision.PROBE_WIDTH_PX, hh),
    )
    left_rect = pygame.FRect(
        Vector2(entity.hitbox.topleft) + Vector2(-Collision.WALL_PROBE_OFFSET_PX, hq),
        (Collision.PROBE_WIDTH_PX, hh),
    )

    on = entity.on_surface
    on["floor"] = on["right"] = on["left"] = False

    for sprite in collision_sprites:
        box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
        if box is None:
            continue
        one_way = getattr(sprite, "one_way", False)
        # A one-way platform only supports an entity resting on its top:
        # an entity inside its body (jumping through) gets no contact.
        if floor_rect.colliderect(box) and (
            not one_way or entity.hitbox.bottom <= box.top + Collision.CONTACT_SKIN_PX
        ):
            on["floor"] = True
        if not one_way:
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


def _flag_crushed(entity: CollisionEntity) -> None:
    """Mark a deep-overlap correction (guarded for foreign test stubs)."""
    if hasattr(entity, "crushed"):
        entity.crushed = True


def _resolve_with_cap(entity: CollisionEntity, correction: float, current: float) -> float:
    """Clamp an axis-nearest fallback correction, flagging crush when capped."""
    if abs(correction) <= Collision.MAX_RESOLVE_PX:
        return current + correction
    _flag_crushed(entity)
    capped = Collision.MAX_RESOLVE_PX if correction > 0 else -Collision.MAX_RESOLVE_PX
    return current + capped


def _try_step_up(
    entity: CollisionEntity,
    sprite: CollisionSprite,
    sprite_box: pygame.Rect | pygame.FRect,
    nearby_sprites: list[CollisionSprite],
) -> bool:
    """Mount a small ledge while grounded instead of stopping (GameFeel)."""
    step_up = GameFeel.STEP_UP_PX
    if step_up <= 0 or not entity.on_surface.get("floor", False):
        return False
    rise = entity.hitbox.bottom - sprite_box.top
    if rise <= 0 or rise > step_up:
        return False
    shifted = entity.hitbox.copy()
    shifted.y -= rise
    if _shift_is_free(entity, shifted, nearby_sprites, ignore=sprite):
        entity.hitbox.y -= rise
        return True
    return False


def _try_corner_correct(
    entity: CollisionEntity,
    sprite_box: pygame.Rect | pygame.FRect,
    nearby_sprites: list[CollisionSprite],
) -> bool:
    """Nudge aside when jumping into a ceiling corner (GameFeel)."""
    corner = GameFeel.CORNER_CORRECT_PX
    if corner <= 0 or entity.velocity.y >= 0:
        return False
    move_axis = float(getattr(entity, "move_axis", 0.0) or 0.0)
    direction = 1.0 if move_axis > 0 else -1.0 if move_axis < 0 else 0.0
    if direction == 0.0:
        return False
    for offset in (direction * corner, -direction * corner):
        shifted = entity.hitbox.copy()
        shifted.x += offset
        if not shifted.colliderect(sprite_box) and _shift_is_free(entity, shifted, nearby_sprites):
            entity.hitbox.x += offset
            return True
    return False


def resolve_collisions(
    entity: CollisionEntity,
    axis: Literal["horizontal", "vertical"],
    nearby_sprites: list[CollisionSprite] | None = None,
) -> None:
    """Resolve collisions between an entity and nearby collidable sprites."""
    if nearby_sprites is None:
        # Pass collision_sprites as positional arg for backward compatibility
        nearby_sprites = get_nearby_sprites(entity, collision_sprites=entity.collision_sprites)

    for sprite in nearby_sprites:
        if not hasattr(sprite, "rect") or sprite.rect is None or not hitbox_collide(entity, sprite):
            continue

        sprite_old = getattr(sprite, "old_hitbox", getattr(sprite, "old_rect", sprite.rect))
        sprite_box = getattr(sprite, "hitbox", sprite.rect)

        # One-way platforms only catch an entity falling onto their top:
        # never a wall from the side, never a ceiling from below.
        if getattr(sprite, "one_way", False) and (
            axis == "horizontal"
            or entity.velocity.y < 0
            or entity.old_hitbox.bottom > sprite_old.top + Collision.CONTACT_SKIN_PX
        ):
            continue

        if (
            axis == "horizontal"
            and entity.hitbox.bottom <= sprite_box.top + Collision.CONTACT_SKIN_PX
        ):
            continue

        was_overlapping = entity.old_hitbox.colliderect(sprite_old)

        if axis == "horizontal":
            if _try_step_up(entity, sprite, sprite_box, nearby_sprites):
                continue
            penetration = min(entity.hitbox.right, sprite_box.right) - max(
                entity.hitbox.left, sprite_box.left
            )
            if not was_overlapping and entity.old_hitbox.right <= sprite_old.left:
                entity.hitbox.right = sprite_box.left
            elif not was_overlapping and entity.old_hitbox.left >= sprite_old.right:
                entity.hitbox.left = sprite_box.right
            elif abs(entity.hitbox.right - sprite_box.left) < abs(
                entity.hitbox.left - sprite_box.right
            ):
                entity.hitbox.right = _resolve_with_cap(
                    entity, sprite_box.left - entity.hitbox.right, entity.hitbox.right
                )
            else:
                entity.hitbox.left = _resolve_with_cap(
                    entity, sprite_box.right - entity.hitbox.left, entity.hitbox.left
                )
            if penetration >= Collision.MIN_PENETRATION_PX:
                entity.velocity.x = 0
        else:
            if _try_corner_correct(entity, sprite_box, nearby_sprites):
                continue
            penetration = min(entity.hitbox.bottom, sprite_box.bottom) - max(
                entity.hitbox.top, sprite_box.top
            )
            if not was_overlapping and entity.old_hitbox.bottom <= sprite_old.top:
                entity.hitbox.bottom = sprite_box.top
            elif not was_overlapping and entity.old_hitbox.top >= sprite_old.bottom:
                entity.hitbox.top = sprite_box.bottom
            elif abs(entity.hitbox.bottom - sprite_box.top) < abs(
                entity.hitbox.top - sprite_box.bottom
            ):
                entity.hitbox.bottom = _resolve_with_cap(
                    entity, sprite_box.top - entity.hitbox.bottom, entity.hitbox.bottom
                )
            else:
                entity.hitbox.top = _resolve_with_cap(
                    entity, sprite_box.bottom - entity.hitbox.top, entity.hitbox.top
                )
            if penetration >= Collision.MIN_PENETRATION_PX:
                entity.velocity.y = 0

    entity.sync_rects()
