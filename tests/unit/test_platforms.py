"""Tests du mouvement des plateformes mobiles (physics/platforms)."""

import pygame
import pytest

from src.core.sprites import MovingPlatform
from src.physics.platforms import update_moving_platform


@pytest.fixture()
def platform() -> MovingPlatform:
    return MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (100.0, 0.0)],
        speed=50.0,
    )


def test_platform_moves_toward_the_next_waypoint(platform: MovingPlatform) -> None:
    x_before = platform.rect.x

    update_moving_platform(platform, 0.5)

    assert platform.rect.x > x_before
    assert platform.rect.x == pytest.approx(25.0)
    assert platform.hitbox.topleft == platform.rect.topleft


def test_platform_ping_pongs_between_waypoints(platform: MovingPlatform) -> None:
    # Arrivée au dernier waypoint : la direction s'inverse.
    for _ in range(10):
        update_moving_platform(platform, 1.0)
    assert platform.current_target == 0
    assert platform.direction == -1

    # Retour au départ : la direction s'inverse à nouveau.
    for _ in range(10):
        update_moving_platform(platform, 1.0)
    assert platform.current_target == 1
    assert platform.direction == 1


def test_platform_snap_remains_deterministic(platform: MovingPlatform) -> None:
    update_moving_platform(platform, 1 / 60)
    first_pass = platform.rect.copy()

    platform.rect.topleft = (0.0, 0.0)
    platform.pos = pygame.math.Vector2(0.0, 0.0)
    platform.current_target = 1
    platform.direction = 1
    update_moving_platform(platform, 1 / 60)

    assert platform.rect.x == pytest.approx(first_pass.x)


def test_platform_without_waypoints_is_static() -> None:
    platform = MovingPlatform(
        (10.0, 10.0), pygame.Surface((64, 32)), waypoints=[], speed=100.0
    )

    update_moving_platform(platform, 1 / 60)

    assert platform.rect.topleft == (10.0, 10.0)