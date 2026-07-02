import pygame


def apply_velocity_friction(entity, friction: float) -> None:
    """Apply friction to an entity's horizontal velocity."""
    entity.velocity.x *= friction


def lerp_velocity(entity, target: float, alpha: float) -> None:
    """Lerp an entity velocity component toward a target value."""
    entity.velocity.x = pygame.math.lerp(entity.velocity.x, target, alpha)
