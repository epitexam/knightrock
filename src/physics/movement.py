import math
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

import pygame
from pygame.math import Vector2

from src.core.settings import (
    Collision,
    GameFeel,
    Input,
    Locomotion,
    PlatformRide,
    Separation,
    Simulation,
)
from src.physics.collisions import (
    CollisionSprite,
    get_nearby_sprites,
    resolve_collisions,
    update_contact_state,
)
from src.physics.gravity import apply_entity_gravity
from src.physics.spatial_hash import SpatialHash

VELOCITY_EPSILON = Locomotion.VELOCITY_EPSILON


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
    """Surface consumed to damp horizontal control after a wall jump.

    ``wall_jump_lock_timer`` is mutated by :func:`apply_horizontal_movement`;
    the two tuning mirrors are read-only.
    """

    @property
    def wall_jump_lock_timer(self) -> float: ...

    @wall_jump_lock_timer.setter
    def wall_jump_lock_timer(self, value: float) -> None: ...

    @property
    def wall_jump_lock_duration(self) -> float: ...

    @property
    def wall_jump_min_lock(self) -> float: ...


class JumpEntity(Protocol):
    """Surface consumed by :func:`resolve_jump`.

    Members the resolver mutates are declared as read/write properties;
    tuning mirrors are read-only. Concrete entities expose them through
    flat delegation properties backed by their controllers.
    """

    velocity: Vector2
    speed: float
    on_surface: dict[str, bool]

    @property
    def jump_buffer_timer(self) -> float: ...

    @jump_buffer_timer.setter
    def jump_buffer_timer(self, value: float) -> None: ...

    @property
    def coyote_timer(self) -> float: ...

    @coyote_timer.setter
    def coyote_timer(self, value: float) -> None: ...

    @property
    def wall_jump_lock_timer(self) -> float: ...

    @wall_jump_lock_timer.setter
    def wall_jump_lock_timer(self, value: float) -> None: ...

    @property
    def wall_jump_lock_duration(self) -> float: ...

    @property
    def jump_height(self) -> float: ...

    @property
    def wall_jump_height(self) -> float: ...

    @property
    def wall_jump_push_multiplier(self) -> float: ...

    @property
    def wall_jumps_left(self) -> float: ...

    @wall_jumps_left.setter
    def wall_jumps_left(self, value: float) -> None: ...

    @property
    def midair_jumps_left(self) -> int: ...

    @midair_jumps_left.setter
    def midair_jumps_left(self, value: int) -> None: ...


class MovableEntity(Protocol):
    velocity: Vector2
    rect: pygame.FRect
    hitbox: pygame.FRect
    old_hitbox: pygame.FRect
    on_surface: dict[str, bool]
    collision_sprites: Iterable[CollisionSprite]
    spatial_hash: SpatialHash | None
    normal_gravity: float
    fall_gravity: float
    slide_gravity: float
    max_slide_speed: float
    max_fall_speed: float
    gravity_scale: float
    fast_fall: bool
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
    carry_backup: tuple[float, float, float, float] | None

    def sync_rects(self) -> None: ...


def apply_horizontal_movement(entity: HorizontalMovementEntity, delta_time: float) -> None:
    """Apply horizontal movement with acceleration and damping."""
    if isinstance(entity, WallJumpLock) and entity.wall_jump_lock_timer > 0:
        elapsed = entity.wall_jump_lock_duration - entity.wall_jump_lock_timer
        entity.wall_jump_lock_timer -= delta_time

        opposing = (entity.move_axis > Input.AXIS_DEADZONE and entity.velocity.x < 0) or (
            entity.move_axis < -Input.AXIS_DEADZONE and entity.velocity.x > 0
        )

        if elapsed >= entity.wall_jump_min_lock and opposing:
            entity.wall_jump_lock_timer = 0.0
        else:
            damp_alpha = 1.0 - math.exp(-Locomotion.WALL_JUMP_DAMPING * delta_time)
            entity.velocity.x += (0 - entity.velocity.x) * damp_alpha
            return

    target_speed = entity.move_axis * entity.speed * entity.combat.movement_multiplier

    if target_speed == 0 and abs(entity.velocity.x) < Locomotion.STOP_SPEED_PX_S:
        entity.velocity.x = 0.0
        return

    control = entity.floor_control if entity.on_surface["floor"] else entity.air_control
    alpha = 1.0 - math.exp(-control * delta_time)
    entity.velocity.x = entity.velocity.x + (target_speed - entity.velocity.x) * alpha

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
    elif (entity.on_surface["left"] or entity.on_surface["right"]) and entity.wall_jumps_left > 0:
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


def apply_jump_cut(entity, divisor: float = GameFeel.JUMP_CUT_DIVISOR) -> None:
    """Cut a rising jump short on button release (variable jump height).

    Neutral at the default divisor (1.0): the velocity is untouched.
    """
    if divisor <= 1.0 or entity.velocity.y >= 0:
        return
    entity.velocity.y /= divisor


def move_entity(entity: MovableEntity, delta_time: float, apply_gravity: bool = True) -> None:
    """Move an entity according to its velocity and the environment.

    Uses spatial hash for O(1) collision lookup (PERF-01/02). Falls back to
    the original O(n) search if spatial_hash is not available.
    """
    if hasattr(entity, "crushed"):
        entity.crushed = False
    # Use spatial hash if available, otherwise fall back to collision_sprites
    spatial_hash = getattr(entity, "spatial_hash", None)
    collision_sprites = getattr(entity, "collision_sprites", None)
    if spatial_hash is not None:
        nearby_sprites = get_nearby_sprites(entity, spatial_hash=spatial_hash)
    else:
        nearby_sprites = get_nearby_sprites(entity, collision_sprites=collision_sprites)

    move_x = entity.velocity.x * delta_time
    steps_x = min(
        Simulation.MAX_SUBSTEPS_PER_AXIS,
        max(1, math.ceil(abs(move_x) / Separation.SUB_STEP_SIZE)),
    )
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
    steps_y = min(
        Simulation.MAX_SUBSTEPS_PER_AXIS,
        max(1, math.ceil(abs(move_y) / Separation.SUB_STEP_SIZE)),
    )
    step_move_y = move_y / steps_y

    for _ in range(steps_y):
        entity.old_hitbox = entity.hitbox.copy()
        entity.hitbox.y += step_move_y
        resolve_collisions(entity, "vertical", nearby_sprites)
        if abs(entity.velocity.y) < VELOCITY_EPSILON:
            entity.velocity.y = 0.0
            break

    _snap_to_ground(entity, nearby_sprites)
    _revert_carry_crush(entity)
    update_contact_state(entity, nearby_sprites)


def _snap_to_ground(entity: MovableEntity, nearby_sprites: list) -> None:
    """Stick to ground within a few pixels instead of floating off edges.

    Neutral at the default distance (0.0): nothing is probed.
    """
    snap = GameFeel.GROUND_SNAP_PX
    if snap <= 0 or entity.velocity.y < 0:
        return

    best: float | None = None
    for sprite in nearby_sprites:
        if getattr(sprite, "one_way", False):
            box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
            if box is None or entity.old_hitbox.bottom > box.top + Collision.CONTACT_SKIN_PX:
                continue
            gap = box.top - entity.hitbox.bottom
            if 0 <= gap <= snap and (best is None or gap < best):
                best = gap
            continue
        box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
        if box is None:
            continue
        overlap_x = min(entity.hitbox.right, box.right) - max(entity.hitbox.left, box.left)
        if overlap_x <= 0:
            continue
        gap = box.top - entity.hitbox.bottom
        if 0 <= gap <= snap and (best is None or gap < best):
            best = gap
    if best is not None:
        entity.hitbox.bottom += best
        entity.velocity.y = 0.0


def _revert_carry_crush(entity: MovableEntity) -> None:
    """Restore the pre-carry position when a platform crushed the entity."""
    crushed = bool(getattr(entity, "crushed", False))
    backup = getattr(entity, "carry_backup", None)
    if hasattr(entity, "carry_backup"):
        entity.carry_backup = None
    if not crushed or backup is None:
        return
    entity.hitbox.x, entity.hitbox.y, entity.hitbox.width, entity.hitbox.height = backup
    entity.velocity.x = 0.0
    entity.velocity.y = 0.0
    entity.sync_rects()


def _sticky_snap(
    entity: PlatformRider,
    platform: MovingPlatform,
    vertical_dist: float,
    platform_dy: float,
) -> bool:
    """Catch a fast-descending platform's new top instead of detaching.

    Neutral at the default factor (0.0): never engages. When engaged, the
    entity drops exactly onto the new surface (never embedded in the pad).
    """
    sticky = PlatformRide.STICKY_FACTOR * max(0.0, platform_dy)
    if sticky <= 0:
        return False
    if not (
        PlatformRide.SNAP_EPSILON_TOP_PX
        < vertical_dist
        <= PlatformRide.SNAP_EPSILON_TOP_PX + sticky
    ):
        return False
    snap = min(platform_dy, platform.hitbox.top - entity.hitbox.bottom)
    if snap <= 0:
        return False
    entity.carry_backup = (
        entity.hitbox.x,
        entity.hitbox.y,
        entity.hitbox.width,
        entity.hitbox.height,
    )
    entity.hitbox.x += platform.hitbox.x - platform.old_hitbox.x
    entity.hitbox.y += snap
    return True


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
        platform_dy = p_box.y - p_old_box.y

        if not (
            -PlatformRide.SNAP_EPSILON_BOTTOM_PX
            <= vertical_dist
            <= PlatformRide.SNAP_EPSILON_TOP_PX
        ):
            if not _sticky_snap(entity, platform, vertical_dist, platform_dy):
                continue
            entity.old_hitbox = entity.hitbox.copy()
            entity.sync_rects()
            break

        overlap = min(entity.hitbox.right, p_old_box.right) - max(
            entity.hitbox.left, p_old_box.left
        )
        if overlap <= 0:
            continue

        platform_dx = p_box.x - p_old_box.x
        platform_dy = p_box.y - p_old_box.y

        if platform_dx == 0 and platform_dy == 0:
            continue

        entity.carry_backup = (
            entity.hitbox.x,
            entity.hitbox.y,
            entity.hitbox.width,
            entity.hitbox.height,
        )
        entity.hitbox.x += platform_dx
        entity.hitbox.y += platform_dy

        entity.old_hitbox = entity.hitbox.copy()

        entity.sync_rects()
        break
