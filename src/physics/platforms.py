import pygame


def update_moving_platform(platform, delta_time: float) -> None:
    """Update a moving platform's position along its waypoints."""
    platform.old_rect = platform.rect.copy()
    platform.old_hitbox = platform.hitbox.copy()

    if not platform.waypoints:
        return

    target = platform.waypoints[platform.current_target]
    direction = target - platform.pos
    distance = direction.length()

    if distance < 1.0:
        platform.pos = pygame.math.Vector2(target)
        platform.current_target += platform.direction
        if platform.current_target in (len(platform.waypoints), -1):
            platform.direction *= -1
            platform.current_target += platform.direction
    else:
        direction.normalize_ip()
        platform.pos += direction * platform.speed * delta_time

    platform.rect.topleft = platform.pos
    platform.hitbox.topleft = platform.pos
    platform.hitbox.width = platform.rect.width
    platform.hitbox.height = platform.rect.height