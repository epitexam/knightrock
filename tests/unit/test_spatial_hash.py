"""SpatialHash: multi-cell registration, re-bucketing, and query margin.

Covers the PERF-01 rewrite: sprites are registered in every cell their
hitbox overlaps, queries visit every covered cell (inflated by
QUERY_MARGIN_PX so boundary-resting sprites are found), and moved sprites
can be re-bucketed with ``update``.
"""

from typing import cast

import pygame

from src.physics.spatial_hash import (
    QUERY_MARGIN_PX,
    SpatialHash,
    SpatialHashMember,
)


class BoxSprite:
    """Minimal spatial-hash member exposing a ``hitbox``."""

    def __init__(self, rect: pygame.FRect) -> None:
        self.hitbox: pygame.Rect | pygame.FRect = rect


class RectOnlySprite:
    """Sprite exposing only a ``rect`` (terrain tiles): registration fallback."""

    def __init__(self, rect: pygame.FRect) -> None:
        self.rect: pygame.Rect | pygame.FRect = rect


def test_sprite_wider_than_cell_is_found_from_its_far_end():
    grid = SpatialHash(cell_size=128)
    wide = BoxSprite(pygame.FRect(0, 0, 300, 64))  # spans columns 0-2
    grid.add(wide)

    found = grid.get_nearby(pygame.FRect(280, 0, 40, 40))  # column 2 only

    assert wide in found


def test_query_finds_sprites_in_every_covered_cell():
    grid = SpatialHash(cell_size=128)
    a = BoxSprite(pygame.FRect(0, 0, 64, 64))
    b = BoxSprite(pygame.FRect(200, 200, 64, 64))
    grid.add_all([a, b])

    found = grid.get_nearby(pygame.FRect(0, 0, 300, 300))  # covers both

    assert a in found
    assert b in found


def test_multicell_sprite_is_returned_once():
    grid = SpatialHash(cell_size=128)
    wide = BoxSprite(pygame.FRect(0, 0, 300, 64))
    grid.add(wide)

    found = grid.get_nearby(pygame.FRect(0, 0, 300, 64))

    assert found.count(wide) == 1


def test_update_rebuckets_moved_sprite():
    grid = SpatialHash(cell_size=128)
    platform = BoxSprite(pygame.FRect(0, 0, 64, 32))
    grid.add(platform)

    platform.hitbox = pygame.FRect(1000, 1000, 64, 32)
    grid.update(platform)

    old_area = grid.get_nearby(pygame.FRect(0, 0, 40, 40))
    assert all(sprite is not platform for sprite in old_area)
    assert platform in grid.get_nearby(pygame.FRect(1000, 1000, 40, 40))


def test_query_margin_finds_sprite_resting_on_cell_boundary():
    grid = SpatialHash(cell_size=128)
    floor_tile = BoxSprite(pygame.FRect(0, 128, 64, 64))  # row 1
    grid.add(floor_tile)

    # Entity resting exactly on the tile top: its hitbox bottom sits on the
    # row boundary, so only the margin extends the query into the tile row.
    assert QUERY_MARGIN_PX > 0
    resting = pygame.FRect(0, 64, 48, 64)
    assert floor_tile in grid.get_nearby(resting)


def test_add_is_idempotent():
    grid = SpatialHash(cell_size=128)
    sprite = BoxSprite(pygame.FRect(0, 0, 64, 64))

    grid.add(sprite)
    grid.add(sprite)

    assert grid.get_nearby(pygame.FRect(0, 0, 64, 64)).count(sprite) == 1


def test_sprite_without_box_is_skipped():
    class Naked:
        pass

    grid = SpatialHash(cell_size=128)
    # Runtime contract: an object without hitbox/rect is skipped, not raised
    # on (regression guard for sprites that only join some groups).
    grid.add(cast(SpatialHashMember, Naked()))
    assert grid.get_nearby(pygame.FRect(0, 0, 64, 64)) == []

    naked_and_box = cast(
        list[SpatialHashMember], [Naked(), BoxSprite(pygame.FRect(0, 0, 10, 10))]
    )
    grid.add_all(naked_and_box)
    assert len(grid.get_nearby(pygame.FRect(0, 0, 64, 64))) == 1


def test_rect_only_sprites_use_rect_fallback():
    grid = SpatialHash(cell_size=128)
    decor = RectOnlySprite(pygame.FRect(0, 0, 64, 64))

    grid.add(decor)

    assert decor in grid.get_nearby(pygame.FRect(0, 0, 64, 64))


def test_remove_and_clear_unregister_sprites():
    grid = SpatialHash(cell_size=128)
    sprite = BoxSprite(pygame.FRect(0, 0, 64, 64))

    grid.add(sprite)
    grid.remove(sprite)
    assert grid.get_nearby(pygame.FRect(0, 0, 64, 64)) == []

    grid.add(sprite)
    grid.clear()
    assert grid.get_nearby(pygame.FRect(0, 0, 64, 64)) == []


def test_move_entity_queries_through_spatial_hash(monkeypatch):
    from src.physics.movement import move_entity
    from tests.unit.test_movement_collision_cache import make_entity

    seen: dict[str, object] = {}
    marker = SpatialHash(cell_size=64)

    def fake_get_nearby(sprite, spatial_hash=None, collision_sprites=None):
        seen["spatial_hash"] = spatial_hash
        seen["collision_sprites"] = collision_sprites
        return []

    monkeypatch.setattr("src.physics.movement.get_nearby_sprites", fake_get_nearby)

    entity = make_entity()
    entity.spatial_hash = marker
    move_entity(entity, 1 / 60)  # type: ignore[arg-type]

    assert seen["spatial_hash"] is marker
    assert seen["collision_sprites"] is None


def test_move_entity_falls_back_without_spatial_hash(monkeypatch):
    from src.physics.movement import move_entity
    from tests.unit.test_movement_collision_cache import make_entity

    seen: dict[str, object] = {}

    def fake_get_nearby(sprite, spatial_hash=None, collision_sprites=None):
        seen["spatial_hash"] = spatial_hash
        seen["collision_sprites"] = collision_sprites
        return []

    monkeypatch.setattr("src.physics.movement.get_nearby_sprites", fake_get_nearby)

    entity = make_entity()  # no spatial_hash attribute -> fallback path
    move_entity(entity, 1 / 60)  # type: ignore[arg-type]

    assert seen["spatial_hash"] is None
    assert seen["collision_sprites"] == []