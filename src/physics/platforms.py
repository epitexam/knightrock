import pygame

_BLOCK_DIVISORS = (1, 2, 4, 8, 16, 32)


def _limit_to_clear(platform, step: pygame.math.Vector2) -> tuple[pygame.math.Vector2, bool]:
    """Shorten a platform's step so it never overlaps static terrain.

    Returns the allowed step (possibly a zero vector) and whether the
    platform was fully blocked.  Other moving platforms and the platform
    itself are ignored: only the world's static colliders block.  Platforms
    without a ``collision_sprites`` reference keep the legacy ghost move.
    """
    static_sprites = getattr(platform, "collision_sprites", None)
    if not static_sprites:
        return step, False
    for divisor in _BLOCK_DIVISORS:
        candidate = platform.hitbox.copy()
        candidate.x += step.x / divisor
        candidate.y += step.y / divisor
        blocked = any(
            (box := getattr(s, "hitbox", getattr(s, "rect", None))) is not None
            and box.colliderect(candidate)
            for s in static_sprites
            if not hasattr(s, "waypoints")
        )
        if not blocked:
            return step / divisor, False
    return step * 0, True


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
        new_target = platform.current_target + platform.direction
        if new_target < 0 or new_target >= len(platform.waypoints):
            # Bounce: reverse direction and target the adjacent waypoint,
            # not the one just arrived at (avoids a double-arrive stall).
            platform.direction *= -1
            new_target = platform.current_target + platform.direction
        platform.current_target = new_target
    else:
        direction.normalize_ip()
        step = direction * platform.speed * delta_time
        step, blocked = _limit_to_clear(platform, step)
        if blocked:
            # Terrain stops the platform: head back toward where it came
            # from instead of pressing into the wall forever.
            platform.direction *= -1
            new_target = platform.current_target + platform.direction
            if 0 <= new_target < len(platform.waypoints):
                platform.current_target = new_target
        platform.pos += step

    platform.rect.topleft = platform.pos
    platform.hitbox.topleft = platform.pos
    platform.hitbox.width = platform.rect.width
    platform.hitbox.height = platform.rect.height
