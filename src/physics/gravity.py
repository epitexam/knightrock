from pygame.math import Vector2


def apply_entity_gravity(entity, delta_time: float) -> None:
    """Apply gravity to an entity based on its current wall-sliding state."""
    if entity._is_wall_sliding():
        entity.velocity.y += entity.slide_gravity * delta_time
        if entity.velocity.y > entity.max_slide_speed:
            entity.velocity.y = entity.max_slide_speed
    else:
        entity.velocity.y += entity.normal_gravity * delta_time
