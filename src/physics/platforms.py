import pygame


def update_moving_platform(platform, delta_time: float) -> None:
    """Update a moving platform's position along its waypoints."""
    platform.old_rect = platform.rect.copy()
    platform.old_hitbox = platform.hitbox.copy()

    if not platform.waypoints:
        return

    target = platform.waypoints[platform.current_target]
    pos = pygame.math.Vector2(platform.rect.topleft)
    direction = target - pos
    distance = direction.length()

    if distance < 1.0:
        platform.rect.topleft = target
        platform.current_target += platform.direction
        if platform.current_target in (len(platform.waypoints), -1):
            platform.direction *= -1
            platform.current_target += platform.direction
    else:
        direction.normalize_ip()
        movement = direction * platform.speed * delta_time
        platform.rect.x += movement.x
        platform.rect.y += movement.y

    platform.hitbox.topleft = platform.rect.topleft
    platform.hitbox.width = platform.rect.width
    platform.hitbox.height = platform.rect.height
