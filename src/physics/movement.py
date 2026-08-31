import math
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

import pygame
from pygame.math import Vector2
from src.core.settings import Separation
from src.physics.collisions import (
    CollisionSprite,
    get_nearby_sprites,
    resolve_collisions,
    update_contact_state,
)
from src.physics.gravity import apply_entity_gravity

VELOCITY_EPSILON = 0.01


class MovementCombat(Protocol):
    @property
    def movement_multiplier(self) -> float: ...


class HorizontalMovementEntity(Protocol):
    velocity: Vector2
    move_axis: float
    speed: float
    floor_control: float
    air_control: float
    on_surface: dict[str, bool]

    @property
    def combat(self) -> MovementCombat: ...


@runtime_checkable
class WallJumpLock(Protocol):
    wall_jump_lock_timer: float
    wall_jump_lock_duration: float
    wall_jump_min_lock: float


class JumpEntity(Protocol):
    velocity: Vector2
    speed: float
    on_surface: dict[str, bool]
    jump_buffer_timer: float
    coyote_timer: float
    jump_height: float
    wall_jump_height: float
    wall_jump_push_multiplier: float
    wall_jump_lock_timer: float
    wall_jump_lock_duration: float
    wall_jumps_left: int | float
    midair_jumps_left: int


class MovableEntity(Protocol):
    velocity: Vector2
    rect: pygame.FRect
    hitbox: pygame.FRect
    old_hitbox: pygame.FRect
    on_surface: dict[str, bool]
    collision_sprites: Iterable[CollisionSprite]
    normal_gravity: float
    fall_gravity: float
    slide_gravity: float
    max_slide_speed: float
    max_fall_speed: float
    drag_coefficient: float
    fall_drag_coefficient: float

    def is_wall_sliding(self) -> bool: ...

    def check_contact(self) -> None: ...

    def sync_rects(self) -> None: ...

    def _on_floor_contact(self) -> None: ...

    def _on_wall_contact(self) -> None: ...


class MovingPlatform(Protocol):
    hitbox: pygame.FRect
    old_hitbox: pygame.FRect


class PlatformRider(Protocol):
    on_surface: dict[str, bool]
    hitbox: pygame.FRect
    old_hitbox: pygame.FRect

    def sync_rects(self) -> None: ...


def apply_horizontal_movement(
    entity: HorizontalMovementEntity, delta_time: float
) -> None:
    """Apply horizontal movement with acceleration and damping."""
    if isinstance(entity, WallJumpLock) and entity.wall_jump_lock_timer > 0:
        elapsed = entity.wall_jump_lock_duration - entity.wall_jump_lock_timer
        entity.wall_jump_lock_timer -= delta_time

        opposing = (
            (entity.move_axis > 0.1 and entity.velocity.x < 0)
            or (entity.move_axis < -0.1 and entity.velocity.x > 0)
        )

        if elapsed >= entity.wall_jump_min_lock and opposing:
            entity.wall_jump_lock_timer = 0.0
        else:
            damp_alpha = 1.0 - math.exp(-10.0 * delta_time)
            entity.velocity.x += (0 - entity.velocity.x) * damp_alpha
            return

    target_speed = (
        entity.move_axis * entity.speed * entity.combat.movement_multiplier
    )

    if target_speed == 0 and abs(entity.velocity.x) < 0.5:
        entity.velocity.x = 0.0
        return

    control = entity.floor_control if entity.on_surface["floor"] else entity.air_control
    alpha = 1.0 - math.exp(-control * delta_time)
    entity.velocity.x = entity.velocity.x + \
        (target_speed - entity.velocity.x) * alpha

    if abs(entity.velocity.x) < VELOCITY_EPSILON:
        entity.velocity.x = 0.0


def resolve_jump(entity: JumpEntity) -> None:
    """Resolve a jump attempt for the entity."""
    if entity.jump_buffer_timer <= 0:
        return

    if entity.coyote_timer > 0:
        entity.velocity.y = -entity.jump_height
        entity.jump_buffer_timer = 0.0
        entity.coyote_timer = 0.0
    elif (
        entity.on_surface["left"] or entity.on_surface["right"]
    ) and entity.wall_jumps_left > 0:
        entity.velocity.y = -entity.wall_jump_height
        push = entity.speed * entity.wall_jump_push_multiplier
        entity.velocity.x = push if entity.on_surface["left"] else -push
        entity.wall_jump_lock_timer = entity.wall_jump_lock_duration
        entity.wall_jumps_left -= 1
        entity.jump_buffer_timer = 0.0
    elif entity.midair_jumps_left > 0:
        entity.velocity.y = -entity.jump_height
        entity.midair_jumps_left -= 1
        entity.jump_buffer_timer = 0.0


def move_entity(
    entity: MovableEntity, delta_time: float, apply_gravity: bool = True
) -> None:
    """Move an entity according to its velocity and the environment.

    Nearby collision sprites are resolved once per call and reused across
    every horizontal/vertical substep and the contact-state pass, instead of
    re-scanning the full terrain for each substep (PERF-01).
    """
    nearby_sprites = get_nearby_sprites(entity, entity.collision_sprites)

    move_x = entity.velocity.x * delta_time
    steps_x = max(1, math.ceil(abs(move_x) / Separation.SUB_STEP_SIZE))
    step_move_x = move_x / steps_x

    for _ in range(steps_x):
        entity.old_hitbox = entity.hitbox.copy()
        entity.hitbox.x += step_move_x
        resolve_collisions(entity, "horizontal", nearby_sprites)

        if abs(entity.velocity.x) < VELOCITY_EPSILON:
            entity.velocity.x = 0.0
            break

    if apply_gravity:
        apply_entity_gravity(entity, delta_time)

    move_y = entity.velocity.y * delta_time
    steps_y = max(1, math.ceil(abs(move_y) / Separation.SUB_STEP_SIZE))
    step_move_y = move_y / steps_y

    for _ in range(steps_y):
        entity.old_hitbox = entity.hitbox.copy()
        entity.hitbox.y += step_move_y
        resolve_collisions(entity, "vertical", nearby_sprites)
        if abs(entity.velocity.y) < VELOCITY_EPSILON:
            entity.velocity.y = 0.0
            break

    update_contact_state(entity, nearby_sprites)


def apply_moving_platform(
    entity: PlatformRider, moving_platforms: Iterable[MovingPlatform]
) -> None:
    """Apply moving-platform support for an entity standing on the platform."""
    if not entity.on_surface["floor"]:
        return

    for platform in moving_platforms:
        p_box = platform.hitbox
        p_old_box = platform.old_hitbox

        vertical_dist = entity.hitbox.bottom - p_old_box.top

        if not (-2 <= vertical_dist <= 4):
            continue

        overlap = min(entity.hitbox.right, p_old_box.right) - max(
            entity.hitbox.left, p_old_box.left
        )
        if overlap <= 0:
            continue

        platform_dx = p_box.x - p_old_box.x
        platform_dy = p_box.y - p_old_box.y

        if platform_dx == 0 and platform_dy == 0:
            continue

        entity.hitbox.x += platform_dx
        entity.hitbox.y += platform_dy

        entity.old_hitbox = entity.hitbox.copy()

        entity.sync_rects()
        break
