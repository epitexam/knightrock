import math
from typing import Any, Iterable

from src.core.settings import Separation
from src.physics.collisions import resolve_collisions
from src.physics.gravity import apply_entity_gravity


def apply_horizontal_movement(entity, delta_time: float) -> None:
    """Apply horizontal movement with acceleration and damping."""
    lock_timer = getattr(entity, "wall_jump_lock_timer", 0.0)
    if lock_timer > 0:
        duration = getattr(entity, "wall_jump_lock_duration", lock_timer)
        min_lock = getattr(entity, "wall_jump_min_lock", 0.0)
        elapsed = duration - lock_timer
        entity.wall_jump_lock_timer = lock_timer - delta_time
        opposing = (
            (entity.move_axis > 0.1 and entity.velocity.x < 0)
            or (entity.move_axis < -0.1 and entity.velocity.x > 0)
        )
        if elapsed >= min_lock and opposing:
            entity.wall_jump_lock_timer = 0.0
        else:
            entity.velocity.x *= max(0.0, 1.0 - 2.0 * delta_time)
            return

    target_speed = entity.move_axis * entity.speed

    if target_speed == 0 and abs(entity.velocity.x) < 0.5:
        entity.velocity.x = 0.0
        return

    control = entity.floor_control if entity.on_surface["floor"] else entity.air_control
    alpha = 1.0 - math.exp(-control * delta_time)
    entity.velocity.x = entity.velocity.x + \
        (target_speed - entity.velocity.x) * alpha

    if abs(entity.velocity.x) < 0.01:
        entity.velocity.x = 0.0


def resolve_jump(entity) -> None:
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
        entity.velocity.y = -entity.wall_jump_height * 1.15
        push = entity.speed * 1.3
        entity.velocity.x = push if entity.on_surface["left"] else -push
        entity.wall_jump_lock_timer = 0.18
        entity.wall_jump_lock_duration = 0.18
        entity.wall_jump_min_lock = 0.08
        entity.wall_jumps_left -= 1
        entity.jump_buffer_timer = 0.0
    elif entity.midair_jumps_left > 0:
        entity.velocity.y = -entity.jump_height
        entity.midair_jumps_left -= 1
        entity.jump_buffer_timer = 0.0


def move_entity(entity, delta_time: float, apply_gravity: bool = True) -> None:
    """Move an entity according to its velocity and the environment."""
    move_x = entity.velocity.x * delta_time
    steps_x = max(1, math.ceil(abs(move_x) / Separation.SUB_STEP_SIZE))
    step_move_x = move_x / steps_x

    for _ in range(steps_x):
        entity.old_hitbox = entity.hitbox.copy()
        entity.hitbox.x += step_move_x
        resolve_collisions(entity, "horizontal")
        if entity.velocity.x == 0:
            break

    if apply_gravity:
        apply_entity_gravity(entity, delta_time)

    move_y = entity.velocity.y * delta_time
    steps_y = max(1, math.ceil(abs(move_y) / Separation.SUB_STEP_SIZE))
    step_move_y = move_y / steps_y

    for _ in range(steps_y):
        entity.old_hitbox = entity.hitbox.copy()
        entity.hitbox.y += step_move_y
        resolve_collisions(entity, "vertical")
        if entity.velocity.y == 0:
            break

    entity.check_contact()


def apply_moving_platform(entity, moving_platforms: Iterable[Any]) -> None:
    """Apply moving-platform support for an entity standing on the platform."""
    if not entity.on_surface["floor"]:
        return

    for platform in moving_platforms:
        p_box = getattr(platform, "hitbox", getattr(platform, "rect", None))
        p_old_box = getattr(platform, "old_hitbox",
                            getattr(platform, "old_rect", None))

        if p_box is None or p_old_box is None:
            continue

        vertical_dist = entity.hitbox.bottom - p_old_box.top
        if not (-2 <= vertical_dist <= 16):
            continue

        overlap = min(entity.hitbox.right, p_old_box.right) - max(
            entity.hitbox.left, p_old_box.left
        )
        if overlap <= 0:
            continue

        platform_dx = p_box.x - p_old_box.x
        platform_dy = p_box.y - p_old_box.y

        entity.hitbox.x += platform_dx
        entity.hitbox.y += platform_dy
        entity.sync_rects()
        break
