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


def test_large_entity_spans_many_cells():
    """A sprite larger than a single cell is registered in all covered cells."""
    grid = SpatialHash(cell_size=32)
    big = BoxSprite(pygame.FRect(0, 0, 100, 100))  # spans 4x4 cells
    grid.add(big)

    # Query from each corner — every cell must return the sprite
    corners = [
        pygame.FRect(0, 0, 1, 1),
        pygame.FRect(99, 0, 1, 1),
        pygame.FRect(0, 99, 1, 1),
        pygame.FRect(99, 99, 1, 1),
    ]
    for corner in corners:
        assert big in grid.get_nearby(corner)


def test_get_nearby_returns_no_false_negatives_at_boundary():
    """QUERY_MARGIN_PX ensures a sprite resting exactly on the cell boundary
    is still found when the query box touches that boundary."""
    grid = SpatialHash(cell_size=128)
    margin = QUERY_MARGIN_PX
    tile = BoxSprite(pygame.FRect(128, 128, 64, 64))  # at boundary
    grid.add(tile)

    # Query box ends exactly at the boundary — margin extends into the tile row
    assert tile in grid.get_nearby(pygame.FRect(64, 128 - margin, 64, 64))


def test_update_does_not_duplicate_sprite():
    """After update(), a sprite must not appear twice in any cell."""
    grid = SpatialHash(cell_size=128)
    sprite = BoxSprite(pygame.FRect(0, 0, 64, 64))
    grid.add(sprite)
    sprite.hitbox = pygame.FRect(64, 0, 64, 64)  # move one cell right
    grid.update(sprite)

    nearby = grid.get_nearby(pygame.FRect(0, 0, 256, 1))  # span both cells
    assert nearby.count(sprite) == 1


def test_remove_unregisters_from_all_cells_and_cleans_empty_buckets():
    """``remove`` pops every cell it occupied and prunes now-empty buckets."""
    grid = SpatialHash(cell_size=128)
    sprite = BoxSprite(pygame.FRect(0, 0, 300, 64))  # spans 3 columns
    grid.add(sprite)

    cell_keys = list(grid._cells_by_sprite[id(sprite)])
    assert len(cell_keys) > 1  # multi-cell registration

    grid.remove(sprite)

    assert id(sprite) not in grid._cells_by_sprite  # deregistered globally
    # Each formerly-occupied bucket is now empty and pruned from the grid
    for cell in cell_keys:
        assert cell not in grid.grid


def test_update_all_rebuckets_every_sprite():
    """``update_all`` re-buckets each sprite exactly once."""
    grid = SpatialHash(cell_size=128)
    a = BoxSprite(pygame.FRect(0, 0, 64, 64))
    b = BoxSprite(pygame.FRect(200, 200, 64, 64))
    grid.add_all([a, b])

    # Move both sprites to new positions
    a.hitbox = pygame.FRect(500, 0, 64, 64)
    b.hitbox = pygame.FRect(0, 500, 64, 64)
    grid.update_all([a, b])

    assert a not in grid.get_nearby(pygame.FRect(0, 0, 64, 64))
    assert a in grid.get_nearby(pygame.FRect(500, 0, 64, 64))
    assert b not in grid.get_nearby(pygame.FRect(200, 200, 64, 64))
    assert b in grid.get_nearby(pygame.FRect(0, 500, 64, 64))


def test_zero_area_box_still_produces_cells():
    """A degenerate (zero-width/height) query box maps to a single cell, not empty."""
    grid = SpatialHash(cell_size=32)
    sprite = BoxSprite(pygame.FRect(10, 10, 1, 1))
    grid.add(sprite)

    cells = grid._cells_for_box(pygame.FRect(10, 10, 0, 0))
    assert len(cells) >= 1  # never empty even for a zero-area box
    # The sprite must be findable from its own degenerate box
    assert sprite in grid.get_nearby(pygame.FRect(10, 10, 0, 0))


def test_remove_is_safe_when_bucket_already_gone():
    """``remove`` must not raise if the internal grid bucket was already pruned."""
    grid = SpatialHash(cell_size=128)
    sprite = BoxSprite(pygame.FRect(0, 0, 64, 64))
    grid.add(sprite)

    # Simulate another sprite's removal having pruned a shared bucket.
    # Manually remove one cell's bucket entry but keep the sprite's cell index.
    cell = grid._cells_for_box(sprite.hitbox)[0]
    del grid.grid[cell]  # bucket gone, but index still records id(sprite)

    # This previously hit the "bucket is None -> continue" branch (line 147).
    grid.remove(sprite)  # must not raise

    assert id(sprite) not in grid._cells_by_sprite


def test_zero_area_box_with_negative_dimensions_never_crashes():
    """A flipped box (left > right, top > bottom) still yields a single cell."""
    grid = SpatialHash(cell_size=64)
    # Flipped box: left=100, right=80 -> x1 < x0 -> collapses to column of x0
    cells = grid._cells_for_box(pygame.FRect(100, 100, -20, -20))
    assert len(cells) == 1  # both axes collapse to a single cell