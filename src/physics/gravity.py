from typing import Protocol, runtime_checkable

import pygame


@runtime_checkable
class GravityEntity(Protocol):
    """Surface consumed by :func:`apply_entity_gravity`.

    Concrete entities expose these kinematics directly (``Entity``);
    test doubles back them with plain attributes.
    """

    velocity: pygame.math.Vector2
    normal_gravity: float
    fall_gravity: float
    slide_gravity: float
    max_slide_speed: float
    max_fall_speed: float
    drag_coefficient: float
    fall_drag_coefficient: float
    gravity_scale: float

    def is_wall_sliding(self) -> bool: ...


def apply_entity_gravity(entity: GravityEntity, delta_time: float) -> None:
    """Apply gravity with air resistance (drag) for a smoother fall.

    Drag coefficients come from the entity (``drag_coefficient`` and
    ``fall_drag_coefficient``); adjust them to modify the fall curve.
    ``gravity_scale`` mods the whole acceleration (juggle softening).
    """
    if entity.is_wall_sliding():
        entity.velocity.y += entity.slide_gravity * delta_time
        if entity.velocity.y > entity.max_slide_speed:
            entity.velocity.y = entity.max_slide_speed
    else:
        grav = entity.fall_gravity if entity.velocity.y > 0 else entity.normal_gravity
        grav *= entity.gravity_scale

        coeff = entity.fall_drag_coefficient if entity.velocity.y > 0 else entity.drag_coefficient

        accel = grav - coeff * entity.velocity.y

        entity.velocity.y += accel * delta_time

        if entity.velocity.y > entity.max_fall_speed:
            entity.velocity.y = entity.max_fall_speed
