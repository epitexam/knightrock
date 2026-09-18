"""One-way platform tiles: solid on top, pass-through everywhere else.

The Tiled ``Platforms`` layer used to be built as pure decor — its tiles
had no collision at all.  They are now one-way platforms: an entity lands
on their top, but jumps through them from below and phases through their
sides, and moving pads pass through them as well.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.core.level.world_builder import _build_one_way_platforms
from src.core.sprite_groups import SpriteGroups
from src.physics.collisions import resolve_collisions, update_contact_state


@pytest.fixture()
def platform_tile() -> SimpleNamespace:
    """A one-way platform tile: 64x64 with its top at y=100."""
    return SimpleNamespace(
        rect=pygame.FRect(100.0, 100.0, 64.0, 64.0),
        hitbox=pygame.FRect(100.0, 100.0, 64.0, 64.0),
        old_hitbox=pygame.FRect(100.0, 100.0, 64.0, 64.0),
        one_way=True,
    )


def make_entity(x: float, y: float, vy: float = 0.0) -> SimpleNamespace:
    hitbox = pygame.FRect(x, y, 40.0, 56.0)
    return SimpleNamespace(
        rect=hitbox.copy(),
        hitbox=hitbox,
        old_hitbox=hitbox.copy(),
        velocity=pygame.Vector2(0.0, vy),
        on_surface={"floor": False, "left": False, "right": False},
        collision_sprites=[],
        sync_rects=Mock(),
        _on_floor_contact=Mock(),
        _on_wall_contact=Mock(),
    )


def test_entity_lands_on_a_one_way_platform(platform_tile: SimpleNamespace) -> None:
    entity = make_entity(110.0, 48.0, vy=100.0)  # hitbox bottom = 104
    entity.old_hitbox.bottom = 95.0  # was fully above the tile last tick

    resolve_collisions(entity, "vertical", nearby_sprites=[platform_tile])

    assert entity.hitbox.bottom == pytest.approx(100.0)
    assert entity.velocity.y == 0.0


def test_entity_jumps_through_a_one_way_platform(platform_tile: SimpleNamespace) -> None:
    entity = make_entity(110.0, 74.0, vy=-100.0)  # hitbox bottom = 130: inside the tile
    entity.old_hitbox.bottom = 140.0

    resolve_collisions(entity, "vertical", nearby_sprites=[platform_tile])

    assert entity.hitbox.bottom == pytest.approx(130.0)
    assert entity.velocity.y == pytest.approx(-100.0)


def test_one_way_platform_is_never_a_wall(platform_tile: SimpleNamespace) -> None:
    entity = make_entity(150.0, 110.0, vy=0.0)
    entity.velocity.x = 100.0
    entity.old_hitbox.bottom = 166.0  # body beside the tile, not above it

    resolve_collisions(entity, "horizontal", nearby_sprites=[platform_tile])

    assert entity.hitbox.x == pytest.approx(150.0)
    assert entity.velocity.x == pytest.approx(100.0)


def test_contact_state_supports_an_entity_resting_on_top(
    platform_tile: SimpleNamespace,
) -> None:
    entity = make_entity(110.0, 44.0)  # hitbox bottom = 100 = tile top
    entity.on_surface = {"floor": False, "left": False, "right": False}

    update_contact_state(entity, [platform_tile])

    assert entity.on_surface["floor"] is True
    assert entity.on_surface["left"] is False
    assert entity.on_surface["right"] is False


def test_contact_state_ignores_an_entity_inside_the_tile(
    platform_tile: SimpleNamespace,
) -> None:
    entity = make_entity(110.0, 74.0)  # hitbox bottom = 130: inside the tile
    entity.on_surface = {"floor": False, "left": False, "right": False}

    update_contact_state(entity, [platform_tile])

    assert entity.on_surface == {"floor": False, "left": False, "right": False}


def test_builder_creates_one_way_tiles_in_the_collision_group() -> None:
    groups = SpriteGroups()
    surf = pygame.Surface((64, 64))

    _build_one_way_platforms([(2, 3, surf)], groups)

    (sprite,) = groups.collision_sprites.sprites()
    assert sprite.one_way is True
    assert sprite.rect.topleft == (128, 192)
