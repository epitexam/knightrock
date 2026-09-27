"""EntityGrid + overlapping_pairs (Phase 3 #1: entity SpatialHash, PERF-02).

Tested guarantees:
- zero false negatives (an overlapping pair is always a candidate);
- pair order identical to the exhaustive loop (i < j, sorted by index);
- brute-force ↔ grid equivalence on a seeded deterministic case;
- the index is bypassed below ``MIN_GRID_MEMBERS``, which changes the cost
  and not the answer.

The last one shapes the rest of the file: a query below the threshold returns
every member, so a test that asserts *pruning* has to use a population large
enough to be indexed. A two-entity grid is the bypass path, and asserting that
it prunes would be asserting the behaviour this change removes.
"""

import random
from types import SimpleNamespace

import pygame

from src.physics.entity_grid import MIN_GRID_MEMBERS, EntityGrid, overlapping_pairs


class GridEntity:
    """Minimal entity stub: hitbox only, what the grid needs."""

    def __init__(self, index: int, x: float, y: float, size: float = 40.0):
        self.index = index
        self.hitbox = pygame.FRect(x, y, size, size)


def spread(count: int, *, step: float = 400.0, start: int = 100) -> list[GridEntity]:
    """``count`` entities far enough apart to occupy distinct cells.

    One per cell is what makes the index worth taking, so this is the layout
    the pruning tests need; a stack of entities in one cell is the layout the
    bypass is for.
    """
    return [GridEntity(index, start + index * step, start) for index in range(count)]


def brute_force_pairs(entities: list[GridEntity]) -> list[tuple[int, int]]:
    """Reference exhaustive implementation, same order as the legacy loops."""
    pairs = []
    for i, ent_a in enumerate(entities):
        for j in range(i + 1, len(entities)):
            if ent_a.hitbox.colliderect(entities[j].hitbox):
                pairs.append((i, j))
    return pairs


def grid_pairs(entities: list[GridEntity], grid: EntityGrid) -> list[tuple[int, int]]:
    return [(a.index, b.index) for a, b in overlapping_pairs(entities, grid)]


def test_rebuild_buckets_every_entity_and_near_finds_them() -> None:
    grid = EntityGrid(cell_size=128)
    entities = spread(MIN_GRID_MEMBERS)
    far = GridEntity(99, 5000, 5000)
    assert grid.rebuild([*entities, far]) == MIN_GRID_MEMBERS + 1

    near_first = grid.near(entities[0].hitbox)
    assert entities[0] in near_first
    assert far not in near_first


def test_member_spanning_cells_is_returned_once() -> None:
    grid = EntityGrid(cell_size=64)
    spanning = GridEntity(0, 60, 60, 8)  # straddling 4 cells
    grid.rebuild([spanning])

    nearby = grid.near(spanning.hitbox)
    assert nearby.count(spanning) == 1


def test_near_never_misses_an_overlapping_entity() -> None:
    """An entity overlapping the query is always a candidate (32px margin)."""
    grid = EntityGrid(cell_size=128)
    seeker = GridEntity(0, 120, 120)
    touching = GridEntity(1, 158, 120)  # 2px overlap
    grid.rebuild([seeker, touching])

    assert touching in grid.near(seeker.hitbox)


def test_overlapping_pairs_matches_brute_force_on_seeded_layout() -> None:
    """Exact equivalence (pairs AND order) with brute force, seeded case."""
    rng = random.Random(42)
    entities = [GridEntity(index, rng.uniform(0, 600), rng.uniform(0, 600)) for index in range(40)]
    grid = EntityGrid(cell_size=128)
    grid.rebuild(entities)

    assert grid_pairs(entities, grid) == brute_force_pairs(entities)


def test_overlapping_pairs_yields_in_ascending_index_order() -> None:
    """For a given i, j come out ascending — like the old double loop."""
    entities = [
        GridEntity(0, 0, 0),
        GridEntity(1, 10, 10),
        GridEntity(2, 20, 20),
        GridEntity(3, 5000, 5000),
    ]
    grid = EntityGrid(cell_size=128)
    grid.rebuild(entities)

    pairs = grid_pairs(entities, grid)
    assert (0, 1) in pairs and (0, 2) in pairs and (1, 2) in pairs
    assert all(i < j for i, j in pairs)
    # no pair with the far entity
    assert all(3 not in (i, j) for i, j in pairs)


def test_overlapping_pairs_skips_members_outside_the_list() -> None:
    """Grid members missing from the filtered sequence are ignored."""
    grid = EntityGrid(cell_size=128)
    listed = [GridEntity(0, 0, 0), GridEntity(1, 10, 10)]
    outsider = GridEntity(99, 5, 5)
    grid.rebuild([*listed, outsider])

    pairs = grid_pairs(listed, grid)
    assert all(99 not in (i, j) for i, j in pairs)
    assert (0, 1) in pairs


def test_clear_empties_the_grid() -> None:
    grid = EntityGrid(cell_size=128)
    entities = spread(MIN_GRID_MEMBERS)
    grid.rebuild(entities)
    grid.clear()

    assert grid.near(entities[0].hitbox) == []


def test_rebuild_after_movement_refreshes_buckets() -> None:
    """Re-bucket after moving: the old cell references nothing anymore."""
    grid = EntityGrid(cell_size=64)
    entities = spread(MIN_GRID_MEMBERS, step=5000.0)
    grid.rebuild(entities)
    entities[0].hitbox.topleft = (5000.0, 5000.0)
    grid.rebuild(entities)

    assert entities[0] in grid.near(entities[0].hitbox)
    far_query = SimpleNamespace()  # unused: query via a hitbox-shaped FRect
    _ = far_query
    assert grid.near(pygame.FRect(0, 0, 40, 40)) == []


# -- when the index is bypassed ------------------------------------------------
#
# Below the threshold, and whenever everything shares a cell, a query answers
# with every member. That is a superset of what the index would have said, and
# every caller filters or re-sorts it, so the pairs are unchanged -- which is
# the property these tests exist to pin.


def test_a_small_population_is_not_indexed() -> None:
    grid = EntityGrid(cell_size=128)
    entities = spread(MIN_GRID_MEMBERS - 1)

    grid.rebuild(entities)

    assert grid.indexed is False
    assert grid.near(entities[0].hitbox) == entities


def test_a_population_in_one_cell_is_not_indexed() -> None:
    """The case a count threshold alone misses: many members, one cell, and
    therefore nothing for the index to prune. A tight melee looks like this."""
    grid = EntityGrid(cell_size=128)
    stacked = [GridEntity(index, 0, 0) for index in range(MIN_GRID_MEMBERS * 2)]

    grid.rebuild(stacked)

    assert grid.indexed is False
    assert len(grid.near(stacked[0].hitbox)) == len(stacked)


def test_a_spread_population_large_enough_is_indexed() -> None:
    grid = EntityGrid(cell_size=128)

    grid.rebuild(spread(MIN_GRID_MEMBERS))

    assert grid.indexed is True


def test_the_bypass_and_the_index_agree_on_the_pairs() -> None:
    """The whole point: same pairs, same order, whichever path answered."""
    rng = random.Random(7)
    entities = [GridEntity(index, rng.uniform(0, 900), rng.uniform(0, 900)) for index in range(30)]
    indexed = EntityGrid(cell_size=128)
    indexed.rebuild(entities)
    assert indexed.indexed is True

    bypassed = EntityGrid(cell_size=128)
    bypassed.rebuild(entities)
    bypassed.indexed = False  # the same population, forced down the other path

    assert grid_pairs(entities, bypassed) == grid_pairs(entities, indexed)
    assert grid_pairs(entities, bypassed) == brute_force_pairs(entities)


def test_append_near_honours_the_callers_seen_set_on_both_paths() -> None:
    """The bypass appends by hand, so its dedupe is its own code."""
    for force_indexed in (True, False):
        grid = EntityGrid(cell_size=128)
        entities = spread(MIN_GRID_MEMBERS)
        grid.rebuild(entities)
        grid.indexed = force_indexed
        nearby: list = []
        seen: set[int] = set()

        grid.append_near(entities[0].hitbox, nearby, seen)
        grid.append_near(entities[0].hitbox, nearby, seen)

        assert len(nearby) == len({id(member) for member in nearby})
        assert entities[0] in nearby


def test_a_cleared_grid_reports_itself_unindexed() -> None:
    grid = EntityGrid(cell_size=128)
    grid.rebuild(spread(MIN_GRID_MEMBERS))

    grid.clear()

    assert grid.indexed is False
    assert grid.near(pygame.FRect(0, 0, 40, 40)) == []
