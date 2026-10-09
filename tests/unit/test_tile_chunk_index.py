"""The frozen tile index: correctness first, then the cost it claims.

The index decides which sprites are *worth asking about*; the camera still
decides which are drawn. So the property that matters is that it is a
conservative superset -- never a subset -- and that it hands them back in
build order, because the order of a tile layer is its Tiled layer order and
reordering it would put a background over the terrain.

The cost claims are asserted structurally rather than by timing: a timing
budget flakes on a shared runner, but "the scan visited every tile and the
index visited a bounded number" does not. ``render_benchmark.py`` carries the
measurements.
"""

import os

import pygame
import pytest

from src.core.input.input_manager import InputManager
from src.core.level.level import Level
from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.core.rendering.camera import Camera
from src.core.rendering.tile_chunk_index import CHUNK_TILES, TileChunkIndex
from src.core.settings import World

TILE = World.TILE_SIZE


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


def tile(column: int, row: int, size: int = TILE) -> pygame.sprite.Sprite:
    sprite = pygame.sprite.Sprite()
    sprite.image = pygame.Surface((size, size), pygame.SRCALPHA)
    sprite.rect = pygame.FRect(column * TILE, row * TILE, size, size)
    return sprite


def grid(columns: int, rows: int, *, chunk_tiles: int = CHUNK_TILES) -> TileChunkIndex:
    """A full tile grid, indexed, with the camera parked at the origin."""
    return TileChunkIndex(
        [tile(column, row) for row in range(rows) for column in range(columns)],
        chunk_tiles=chunk_tiles,
    )


def viewport_at(column: float, row: float, columns: float = 4, rows: float = 4):
    return pygame.FRect(column * TILE, row * TILE, columns * TILE, rows * TILE)


def test_a_sprite_inside_the_viewport_is_always_a_candidate() -> None:
    """The whole point: the index must never hide a visible sprite."""
    index = grid(20, 20)
    viewport = viewport_at(5.5, 5.5, 6, 6)
    candidates = {id(sprite) for sprite in index.candidates(viewport)}

    missing = [
        sprite
        for sprite in index._ordered
        if sprite.rect.colliderect(viewport) and id(sprite) not in candidates
    ]
    assert missing == []


def test_a_sprite_straddling_a_chunk_border_is_registered_on_both_sides() -> None:
    """The failure this guards is a one-chunk gap, which reads as a black line."""
    index = TileChunkIndex([tile(0, 0, size=TILE * CHUNK_TILES * 2)], chunk_tiles=CHUNK_TILES)
    straddler = index._ordered[0]

    assert index.candidates(pygame.FRect(0.0, 0.0, TILE, TILE)) == [straddler]
    assert index.candidates(pygame.FRect(TILE * CHUNK_TILES, 0.0, TILE, TILE)) == [straddler]
    # And the far chunk, which the sprite's right edge only just reaches.
    assert index.candidates(pygame.FRect(TILE * CHUNK_TILES * 2 - 1.0, 0.0, 4.0, 4.0)) == [
        straddler
    ]


def test_a_negative_coordinate_lands_below_the_origin_not_on_it() -> None:
    """``int()`` truncates towards zero, which would file a sprite at y = -64
    into the same row as y = 0 and leave the row above it unqueried."""
    index = TileChunkIndex([tile(-1, -1), tile(0, 0)], chunk_tiles=1)
    above, origin = index._ordered

    assert index.candidates(pygame.FRect(-TILE, -TILE, TILE / 2, TILE / 2)) == [above]
    assert index.candidates(pygame.FRect(0.0, 0.0, TILE / 2, TILE / 2)) == [origin]


def test_the_viewport_is_padded_so_a_camera_landing_on_a_border_is_not_truncated() -> None:
    """A viewport ending exactly on a chunk border still covers the chunk the
    camera has just entered, because the interpolated offset makes that the
    normal case rather than the exceptional one."""
    index = TileChunkIndex([tile(0, 0), tile(1, 0)], chunk_tiles=1)
    first, second = index._ordered

    assert index.candidates(pygame.FRect(0.0, 0.0, TILE, TILE)) == [first, second]


def test_candidates_come_back_in_build_order() -> None:
    """Draw order is the Tiled layer order; the index must not reshuffle it."""
    order = [tile(column, 0) for column in (30, 2, 17, 5, 40)]
    index = TileChunkIndex(order)
    wide = pygame.FRect(0.0, 0.0, 60 * TILE, 4 * TILE)

    assert index.candidates(wide) == order


def test_a_sprite_reachable_from_two_chunks_is_returned_once() -> None:
    """Straddlers land in every chunk they touch; the merge must deduplicate."""
    index = TileChunkIndex([tile(0, 0, size=TILE * CHUNK_TILES * 3)], chunk_tiles=CHUNK_TILES)
    straddler = index._ordered[0]

    wide = pygame.FRect(0.0, 0.0, TILE * CHUNK_TILES * 3, TILE * CHUNK_TILES * 3)

    assert index.candidates(wide) == [straddler]


def test_a_sprite_with_no_rectangle_is_offered_rather_than_dropped() -> None:
    """pygame allows an unset rect; the linear path treats it as empty, so the
    index has to offer it too rather than lose it silently."""
    orphan = pygame.sprite.Sprite()
    orphan.image = pygame.Surface((8, 8), pygame.SRCALPHA)
    index = TileChunkIndex([orphan], chunk_tiles=1)

    assert index.candidates(pygame.FRect(9e9, 9e9, 8, 8)) == [orphan]
    assert index.owns(orphan)


def test_the_candidate_count_is_bounded_by_the_view_not_the_level() -> None:
    """The reason the index exists, asserted without a clock.

    Both planes hold the *same* tiles in view; the large one also holds ten
    times as many far away. If the candidate count tracked the level instead
    of the view, this is the assertion that would fail.
    """
    viewport = viewport_at(0.0, 0.0, 18, 10)
    in_view = [tile(column, row) for row in range(10) for column in range(18)]
    small = TileChunkIndex(in_view)
    large = TileChunkIndex(
        [*in_view, *(tile(40 + index % 60, 40 + index // 60) for index in range(22000))]
    )

    assert len(small) < len(large) / 10
    assert len(small.candidates(viewport)) == len(large.candidates(viewport))


def test_a_smaller_chunk_selects_fewer_candidates() -> None:
    """Chunk size trades the number of buckets against over-selection: a
    smaller chunk over-selects less, at the cost of more buckets to touch."""
    viewport = viewport_at(0.0, 0.0, 18, 10)
    coarse = grid(40, 30, chunk_tiles=16).candidates(viewport)
    fine = grid(40, 30, chunk_tiles=2).candidates(viewport)

    assert len(fine) < len(coarse)
    # A chunk is 2 tiles, the viewport is 18x10, padded by one chunk per side:
    # at most 11x7 chunks of 2x2 cells each, on a fully dense grid.
    assert len(fine) <= 11 * 7 * 2 * 2
    assert len(fine) < 40 * 30, "the index must beat the level it indexes"


def test_owns_answers_for_the_whole_plane_and_for_nothing_else() -> None:
    index = grid(4, 4)
    stranger = tile(0, 0)

    assert all(index.owns(sprite) for sprite in index._ordered)
    assert not index.owns(stranger)


def test_a_degenerate_chunk_geometry_is_refused() -> None:
    with pytest.raises(ValueError, match="tile size"):
        TileChunkIndex([], tile_size=0.0)
    with pytest.raises(ValueError, match="one tile per side"):
        TileChunkIndex([], chunk_tiles=0)


def test_the_index_survives_a_camera_that_moved_between_frames() -> None:
    """Built once, queried forever: the index must not cache a viewport."""
    index = grid(40, 30)
    camera = Camera()
    camera.set_world_size(40 * TILE, 30 * TILE)
    seen: list[int] = []

    for column in (0, 10, 20, 30):
        camera.offset.update(column * TILE, 0.0)
        camera.begin_frame(1.0)
        seen.append(len(index.candidates(camera.viewport)))

    assert seen == [
        len(index.candidates(viewport_at(column, 0.0, 18, 10))) for column in (0, 10, 20, 30)
    ]
    assert len(set(seen)) > 1, "the camera moved, so the answers must differ"


def test_candidates_stay_near_the_viewport_rather_than_covering_the_level() -> None:
    """An index that returned the whole plane would be correct and useless.

    Every candidate must at least be within one chunk of the viewport, which
    is the slack the chunking is allowed to introduce.
    """
    index = grid(40, 30)
    camera = Camera()
    camera.set_world_size(40 * TILE, 30 * TILE)
    camera.offset.update(7.5 * TILE, 3.25 * TILE)
    camera.begin_frame(1.0)
    slack = CHUNK_TILES * TILE
    reach = pygame.FRect(
        camera.viewport.left - slack,
        camera.viewport.top - slack,
        camera.viewport.width + 2 * slack,
        camera.viewport.height + 2 * slack,
    )

    candidates = index.candidates(camera.viewport)
    padded_cells = (18 // CHUNK_TILES + 2) * (10 // CHUNK_TILES + 2) * CHUNK_TILES**2

    assert candidates, "the fixture must put something on screen"
    assert len(candidates) <= padded_cells, "the padding is one chunk per side, no more"
    for sprite in candidates:
        assert sprite.rect.colliderect(reach), f"{sprite.rect} is nowhere near the viewport"


def test_every_visible_sprite_is_a_candidate_at_every_camera_position() -> None:
    """The property that makes the cull safe, swept across the level.

    One position could pass by luck -- the plane is a regular grid, so a
    viewport aligned to it has no straddlers. Walking the camera across chunk
    boundaries and back covers the misaligned cases, which are the ones that
    would drop a line of tiles.
    """
    index = grid(40, 30)
    camera = Camera()
    camera.set_world_size(40 * TILE, 30 * TILE)

    for column in range(0, 22):
        for row in (0, 1, 2, 3):
            offset = column * TILE + 0.5 * TILE, row * TILE + 0.5 * TILE
            camera.offset.update(*offset)
            camera.begin_frame(1.0)
            candidates = {id(sprite) for sprite in index.candidates(camera.viewport)}
            missing = [
                sprite
                for sprite in index._ordered
                if sprite.rect.colliderect(camera.viewport) and id(sprite) not in candidates
            ]
            assert missing == [], f"dropped tiles at offset {offset}"


# -- the real registered level -------------------------------------------------
#
# The unit tests above use synthetic planes because they can be made to break on
# demand. These use the level that actually ships, because the invariant worth
# protecting is a property of the world builder: every sprite a frame can draw
# is in exactly one plane, and the frozen one holds nothing that moves.


@pytest.fixture(scope="module")
def real_level() -> Level:
    surface = pygame.Surface((1280, 720))
    return Level(surface, LevelManager(LEVEL_PATHS).get(0), InputManager())


def test_the_real_level_installs_an_index(real_level: Level) -> None:
    """A level that silently fell back to the scan would look identical and
    cost four times as much at 22 000 tiles, which is why this is asserted."""
    level = real_level

    assert len(level.groups.static_sprites) > 500
    assert level.renderer._static_index is not None


def test_the_draw_planes_partition_the_real_level(real_level: Level) -> None:
    """No sprite in two planes (drawn twice) and none in none (never drawn)."""
    level = real_level
    groups = level.groups
    planes = [tuple(groups.static_sprites), tuple(groups.all_sprites), tuple(groups.fg_sprites)]

    seen: set[int] = set()
    for plane in planes:
        for sprite in plane:
            assert id(sprite) not in seen, f"{sprite!r} is in two draw planes"
            seen.add(id(sprite))

    assert len(seen) == sum(len(plane) for plane in planes)
    assert len(groups.every_sprite) == len(seen)
    assert len(groups.every_sprite) > 900, "the shipped level's sprite count moved"


def test_nothing_that_moves_is_in_the_frozen_plane(real_level: Level) -> None:
    """The check ``Level`` runs before installing, asserted on real data."""
    level = real_level
    static_ids = {id(sprite) for sprite in level.groups.static_sprites}

    for plane in level._moving_planes():
        assert not any(id(sprite) in static_ids for sprite in plane)


def test_a_refused_index_falls_back_to_the_linear_scan(real_level: Level) -> None:
    """The level promises the linear cull when it refuses the index.

    Refusing without a fallback left the frozen plane empty: the terrain
    vanished and nothing at all logged it as wrong, because the warning said
    the cull was kept. The scan is the same result, only slower.
    """
    level = real_level
    groups = level.groups
    renderer = level.renderer
    renderer.set_static_planes(None, None)

    assert list(renderer._static_plane(groups, None, renderer.camera.viewport)) == list(
        groups.static_sprites
    )


def test_the_frozen_plane_still_answers_collision_queries(real_level: Level) -> None:
    """Moving the tiles out of ``all_sprites`` must not have moved them out of
    the physics: a level that cannot be collided with is not a level.

    The terrain is in both planes, and the collision plane also holds things
    that move -- the player, the moving platforms -- so neither group contains
    the other. What has to hold is that the terrain is in both.
    """
    level = real_level
    groups = level.groups
    static_ids = {id(sprite) for sprite in groups.static_sprites}
    collidable_static = [sprite for sprite in groups.collision_sprites if id(sprite) in static_ids]

    assert len(groups.collision_sprites) > 400
    assert len(collidable_static) > 400, "the terrain left the collision plane"
    assert len(collidable_static) < len(groups.collision_sprites), (
        "the collision plane also holds the player and the moving platforms"
    )
    assert len(collidable_static) < len(groups.static_sprites), (
        "some tile layers are decorative and are not collidable"
    )
    probe = collidable_static[len(collidable_static) // 2].rect
    assert level.spatial_hash.get_nearby(probe), "the terrain must still be in the collision grid"
