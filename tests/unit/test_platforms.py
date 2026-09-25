"""Moving platform motion tests (physics/platforms)."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.core.level.systems.platform_system import PlatformSystem
from src.core.sprite_groups import SpriteGroups
from src.core.sprites import MovingPlatform, Sprite
from src.physics.platforms import update_moving_platform
from src.physics.spatial_hash import SpatialHash


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
    # Arrival at the last waypoint: direction reverses.
    for _ in range(10):
        update_moving_platform(platform, 1.0)
    assert platform.current_target == 0
    assert platform.direction == -1

    # Back at the start: direction reverses again.
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
    platform = MovingPlatform((10.0, 10.0), pygame.Surface((64, 32)), waypoints=[], speed=100.0)

    update_moving_platform(platform, 1 / 60)

    assert platform.rect.topleft == (10.0, 10.0)


def test_platform_stops_at_static_terrain_instead_of_phasing_through() -> None:
    blocker = SimpleNamespace(hitbox=pygame.FRect(90.0, 0.0, 64.0, 32.0))
    platform = MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (200.0, 0.0)],
        speed=50.0,
        collision_sprites=[blocker],
    )

    max_x = platform.rect.x
    for _ in range(40):
        update_moving_platform(platform, 0.5)
        assert not platform.hitbox.colliderect(blocker.hitbox)
        max_x = max(max_x, platform.rect.x)

    # The pad pressed against the wall, turned around, and never reached
    # the far waypoint at x=200.
    assert max_x <= 90.0
    assert platform.rect.x <= 30.0


@pytest.mark.parametrize("use_hash", [False, True])
def test_platform_blocked_by_terrain_behaves_the_same_through_the_spatial_hash(
    use_hash: bool,
) -> None:
    """The grid must not change where a platform stops.

    The terrain check asks *whether* something blocks, never in what order, so
    the grid query can only differ in cost. This pins that: a level wired
    through the grid must stop at exactly the same place as a bare scan.
    """
    blocker = SimpleNamespace(hitbox=pygame.FRect(90.0, 0.0, 64.0, 32.0))
    groups = SpriteGroups()
    tile = Sprite((0.0, 0.0), surf=pygame.Surface((64, 32)))
    tile.hitbox = pygame.FRect(90.0, 0.0, 64.0, 32.0)
    groups.collision_sprites.add(tile)
    blocker = tile
    platform = MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (200.0, 0.0)],
        speed=50.0,
        collision_sprites=groups.collision_sprites,
    )
    if use_hash:
        grid = SpatialHash(cell_size=128)
        grid.add_all(groups.collision_sprites)
        platform.spatial_hash = grid

    trace: list[float] = []
    for _ in range(40):
        update_moving_platform(platform, 0.5)
        assert not platform.hitbox.colliderect(blocker.hitbox)
        trace.append(platform.rect.x)

    assert max(trace) <= 90.0
    assert platform.rect.x <= 30.0
    # Same motion as the bare-scan path, tick for tick.
    reference = MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (200.0, 0.0)],
        speed=50.0,
        collision_sprites=groups.collision_sprites,
    )
    expected: list[float] = []
    for _ in range(40):
        update_moving_platform(reference, 0.5)
        expected.append(reference.rect.x)
    assert trace == expected


def test_platform_without_collision_reference_keeps_legacy_ghost_move() -> None:
    blocker = SimpleNamespace(hitbox=pygame.FRect(90.0, 0.0, 64.0, 32.0))
    platform = MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (200.0, 0.0)],
        speed=50.0,
    )

    overlapped = False
    for _ in range(10):
        update_moving_platform(platform, 0.5)
        overlapped = overlapped or platform.hitbox.colliderect(blocker.hitbox)

    assert overlapped


def test_platform_system_pushes_entities_the_pad_moves_into() -> None:
    groups = SpriteGroups()
    pad = MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (200.0, 0.0)],
        speed=50.0,
    )
    groups.moving_platforms.add(pad)
    bystander = pygame.sprite.Sprite()
    bystander.hitbox = pygame.FRect(80.0, -24.0, 40.0, 56.0)
    bystander.sync_rects = Mock()
    groups.entity_sprites.add(bystander)

    PlatformSystem(groups, SpatialHash()).process(0.5)

    assert bystander.hitbox.x == pytest.approx(105.0)


def test_platform_system_pushes_entities_vertically_for_descending_pads() -> None:
    groups = SpriteGroups()
    pad = MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (0.0, 200.0)],
        speed=50.0,
    )
    groups.moving_platforms.add(pad)
    bystander = pygame.sprite.Sprite()
    bystander.hitbox = pygame.FRect(8.0, 40.0, 40.0, 56.0)
    bystander.sync_rects = Mock()
    groups.entity_sprites.add(bystander)

    PlatformSystem(groups, SpatialHash()).process(0.5)

    assert bystander.hitbox.y == pytest.approx(65.0)


def test_platform_system_never_pushes_entities_already_overlapping() -> None:
    groups = SpriteGroups()
    pad = MovingPlatform(
        (0.0, 0.0),
        pygame.Surface((64, 32)),
        waypoints=[(0.0, 0.0), (200.0, 0.0)],
        speed=50.0,
    )
    groups.moving_platforms.add(pad)
    overlapping = pygame.sprite.Sprite()
    overlapping.hitbox = pygame.FRect(10.0, -20.0, 40.0, 56.0)
    overlapping.sync_rects = Mock()
    groups.entity_sprites.add(overlapping)

    PlatformSystem(groups, SpatialHash()).process(0.5)

    assert overlapping.hitbox.x == pytest.approx(10.0)
