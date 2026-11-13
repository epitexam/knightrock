import math
from typing import Any


def apply_velocity_friction(entity: Any, friction: float, delta_time: float) -> None:
    """Apply framerate-independent friction to an entity's horizontal velocity."""
    if abs(entity.velocity.x) < 0.01:
        entity.velocity.x = 0.0
        return

    alpha = 1.0 - math.exp(-friction * delta_time)
    entity.velocity.x += (0 - entity.velocity.x) * alpha


def lerp_velocity(entity: Any, target: float, speed: float, delta_time: float) -> None:
    """Framerate-independent lerp an entity velocity component toward a target value."""
    alpha = 1.0 - math.exp(-speed * delta_time)
    entity.velocity.x += (target - entity.velocity.x) * alpha


def apply_slide_friction(entity: Any, friction: float, drag: float, delta_time: float) -> None:
    """Slow a body sliding on the ground: a constant grip plus a speed-proportional drag.

    ``dv/dt = -(friction + drag * |v|)``, integrated exactly so the curve does
    not depend on the frame rate. The two terms do different jobs. The drag
    takes the edge off a hard shove at once, which is what makes it read as a
    body with weight; the constant grip is what *stops* it, in finite time and
    at a speed that reaches exactly zero. An exponential ease alone never
    arrives: it crawls for the last third of its travel and has to be snapped
    to rest at an arbitrary threshold.

    Parameters
    ----------
    friction : float
        Constant deceleration in px/s^2.
    drag : float
        Speed-proportional deceleration in 1/s; 0 leaves a pure constant brake.
    """
    velocity = entity.velocity.x
    speed = abs(velocity)
    if speed == 0.0:
        return
    if drag > 0.0:
        terminal = friction / drag
        speed = (speed + terminal) * math.exp(-drag * delta_time) - terminal
    else:
        speed -= friction * delta_time
    entity.velocity.x = math.copysign(max(speed, 0.0), velocity)
