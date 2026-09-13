"""EntityGrid + overlapping_pairs (Phase 3 #1 : SpatialHash des entités, PERF-02).

Garanties testées :
- zéro faux négatif (une paire qui se chevauche est toujours candidate) ;
- ordre des paires identique à la boucle exhaustive (i < j, tri par index) ;
- équivalence brute-force ↔ grid sur un cas seedé déterministe.
"""

import random
from types import SimpleNamespace

import pygame

from src.physics.entity_grid import EntityGrid, overlapping_pairs


class GridEntity:
    """Minimal entity stub: hitbox only, what the grid needs."""

    def __init__(self, index: int, x: float, y: float, size: float = 40.0):
        self.index = index
        self.hitbox = pygame.FRect(x, y, size, size)


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
    a = GridEntity(0, 0, 0)
    b = GridEntity(1, 5000, 5000)
    assert grid.rebuild([a, b]) == 2

    near_a = grid.near(a.hitbox)
    assert a in near_a
    assert b not in near_a


def test_member_spanning_cells_is_returned_once() -> None:
    grid = EntityGrid(cell_size=64)
    spanning = GridEntity(0, 60, 60, 8)  # à cheval sur 4 cellules
    grid.rebuild([spanning])

    nearby = grid.near(spanning.hitbox)
    assert nearby.count(spanning) == 1


def test_near_never_misses_an_overlapping_entity() -> None:
    """Une entité qui chevauche la requête est toujours candidate (marge 32px)."""
    grid = EntityGrid(cell_size=128)
    seeker = GridEntity(0, 120, 120)
    touching = GridEntity(1, 158, 120)  # chevauche de 2px
    grid.rebuild([seeker, touching])

    assert touching in grid.near(seeker.hitbox)


def test_overlapping_pairs_matches_brute_force_on_seeded_layout() -> None:
    """Équivalence exacte (paires ET ordre) avec le brute-force, cas seedé."""
    rng = random.Random(42)
    entities = [GridEntity(index, rng.uniform(0, 600), rng.uniform(0, 600)) for index in range(40)]
    grid = EntityGrid(cell_size=128)
    grid.rebuild(entities)

    assert grid_pairs(entities, grid) == brute_force_pairs(entities)


def test_overlapping_pairs_yields_in_ascending_index_order() -> None:
    """Pour un même i, les j sortent croissants — comme l'ancienne double boucle."""
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
    # aucun duo avec l'entité lointaine
    assert all(3 not in (i, j) for i, j in pairs)


def test_overlapping_pairs_skips_members_outside_the_list() -> None:
    """Les membres du grid absents de la séquence filtrée sont ignorés."""
    grid = EntityGrid(cell_size=128)
    listed = [GridEntity(0, 0, 0), GridEntity(1, 10, 10)]
    outsider = GridEntity(99, 5, 5)
    grid.rebuild([*listed, outsider])

    pairs = grid_pairs(listed, grid)
    assert all(99 not in (i, j) for i, j in pairs)
    assert (0, 1) in pairs


def test_clear_empties_the_grid() -> None:
    grid = EntityGrid(cell_size=128)
    entity = GridEntity(0, 0, 0)
    grid.rebuild([entity])
    grid.clear()

    assert entity not in grid.near(entity.hitbox)


def test_rebuild_after_movement_refreshes_buckets() -> None:
    """Re-bucket après déplacement : l'ancienne cellule ne référence plus rien."""
    grid = EntityGrid(cell_size=64)
    entity = GridEntity(0, 0, 0)
    grid.rebuild([entity])
    entity.hitbox.topleft = (5000.0, 5000.0)
    grid.rebuild([entity])

    assert entity in grid.near(entity.hitbox)
    far_query = SimpleNamespace()  # unused: query via a hitbox-shaped FRect
    _ = far_query
    assert grid.near(pygame.FRect(0, 0, 40, 40)) == []
