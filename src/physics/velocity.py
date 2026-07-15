import math
import pygame

def apply_velocity_friction(entity, friction: float, delta_time: float) -> None:
    """Apply framerate-independent friction to an entity's horizontal velocity."""
    if abs(entity.velocity.x) < 0.01:
        entity.velocity.x = 0.0
        return
        
    alpha = 1.0 - math.exp(-friction * delta_time)
    entity.velocity.x += (0 - entity.velocity.x) * alpha


def lerp_velocity(entity, target: float, speed: float, delta_time: float) -> None:
    """Framerate-independent lerp an entity velocity component toward a target value."""
    alpha = 1.0 - math.exp(-speed * delta_time)
    entity.velocity.x += (target - entity.velocity.x) * alpha