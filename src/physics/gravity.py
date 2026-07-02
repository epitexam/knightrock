from pygame.math import Vector2


def apply_entity_gravity(entity, delta_time: float) -> None:
    """
    Apply gravity with air resistance (drag) for smoother fall.
    Les coefficients de drag sont lus depuis l'entité (attributs drag_coefficient
    et fall_drag_coefficient). Ajustez-les pour modifier la courbe de chute.
    """
    if entity._is_wall_sliding():

        entity.velocity.y += entity.slide_gravity * delta_time
        if entity.velocity.y > entity.max_slide_speed:
            entity.velocity.y = entity.max_slide_speed
    else:

        grav = entity.fall_gravity if entity.velocity.y > 0 else entity.normal_gravity

        drag = getattr(entity, 'drag_coefficient', 0.08)
        fall_drag = getattr(entity, 'fall_drag_coefficient', 0.12)
        coeff = fall_drag if entity.velocity.y > 0 else drag

        accel = grav - coeff * entity.velocity.y

        entity.velocity.y += accel * delta_time

        if entity.velocity.y > entity.max_fall_speed:
            entity.velocity.y = entity.max_fall_speed
