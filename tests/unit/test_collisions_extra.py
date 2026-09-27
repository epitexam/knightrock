"""Additional tests for physics/collisions: update_contact_state and spatial hash path."""

from types import SimpleNamespace

import pygame

from src.physics.collisions import get_nearby_sprites, update_contact_state
from src.physics.spatial_hash import SpatialHash


class _ContactEntity:
    """Minimal entity for update_contact_state testing."""

    def __init__(self, hitbox: pygame.FRect) -> None:
        self.hitbox = hitbox
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.floor_contacts = 0
        self.wall_contacts = 0

    def _on_floor_contact(self) -> None:
        self.floor_contacts += 1

    def _on_wall_contact(self) -> None:
        self.wall_contacts += 1


def _tile(hitbox: pygame.FRect) -> SimpleNamespace:
    return SimpleNamespace(
        hitbox=hitbox,
        old_hitbox=hitbox.copy(),
        rect=hitbox,
    )


def test_update_contact_state_detects_floor() -> None:
    entity = _ContactEntity(pygame.FRect(50, 190, 48, 56))
    tile = _tile(pygame.FRect(0, 200, 400, 64))
    update_contact_state(entity, [tile])
    assert entity.on_surface["floor"] is True


def test_update_contact_state_detects_left_wall() -> None:
    entity = _ContactEntity(pygame.FRect(0, 100, 48, 56))
    tile = _tile(pygame.FRect(-20, 80, 24, 56))
    update_contact_state(entity, [tile])
    assert entity.on_surface["left"] is True


def test_update_contact_state_detects_right_wall() -> None:
    entity = _ContactEntity(pygame.FRect(100, 100, 48, 56))
    tile = _tile(pygame.FRect(148, 80, 24, 56))
    update_contact_state(entity, [tile])
    assert entity.on_surface["right"] is True


def test_update_contact_state_resets_flags_when_no_collision() -> None:
    entity = _ContactEntity(pygame.FRect(50, 50, 48, 56))
    entity.on_surface = {"floor": True, "left": True, "right": True}
    far_tile = _tile(pygame.FRect(5000, 5000, 64, 64))
    update_contact_state(entity, [far_tile])
    assert entity.on_surface == {"floor": False, "left": False, "right": False}


def test_update_contact_state_calls_floor_callback() -> None:
    entity = _ContactEntity(pygame.FRect(50, 190, 48, 56))
    tile = _tile(pygame.FRect(0, 200, 400, 64))
    update_contact_state(entity, [tile])
    assert entity.floor_contacts == 1


def test_update_contact_state_calls_wall_callback() -> None:
    """Wall contact triggers callback when no floor contact."""
    entity = _ContactEntity(pygame.FRect(0, 100, 48, 56))
    tile = _tile(pygame.FRect(-20, 80, 24, 56))
    update_contact_state(entity, [tile])
    assert entity.wall_contacts == 1


def test_update_contact_state_skips_none_box_sprite() -> None:
    """Sprites with neither hitbox nor rect are silently skipped."""
    entity = _ContactEntity(pygame.FRect(50, 190, 48, 56))
    bad_sprite = SimpleNamespace()  # no hitbox, no rect
    tile = _tile(pygame.FRect(0, 200, 400, 64))
    update_contact_state(entity, [bad_sprite, tile])
    assert entity.on_surface["floor"] is True


# --- The spatial hash is a performance device, never a behaviour -------------
#
# The grid is an *optional* fast path. ``get_nearby_sprites`` answers the same
# question without it, by scanning every collider in the level, and the two
# answers have to agree — otherwise wiring an entity to the grid (or failing to)
# would change the physics, and the failure mode would be invisible: no
# exception, no log, just a different game.
#
# So: a grid that is wired is faster, a grid that is missing is slower, and
# neither may be *different*. These tests pin that equivalence, so a future
# change to either side of it fails loudly instead of quietly shipping.


def _tile(hitbox: pygame.FRect) -> SimpleNamespace:
    return SimpleNamespace(hitbox=hitbox, old_hitbox=hitbox.copy(), rect=hitbox)


def _prober(hitbox: pygame.FRect) -> SimpleNamespace:
    """The minimum ``get_nearby_sprites`` reads: a hitbox and nothing else."""
    return SimpleNamespace(hitbox=hitbox)


#: Terrain chosen so the fixture can *fail*.
#:
#: The margin-only tile matters more than it looks. A body sitting wholly
#: inside one cell covers that cell at zero margin, so deleting
#: ``QUERY_MARGIN_PX`` would change nothing and the parity assertion would
#: still pass — a test that cannot fail. ``_BODY`` is therefore placed inside a
#: single cell, and ``_LEVEL[2]`` lives in a *neighbouring* cell that only the
#: inflated query reaches. With the margin deleted, the grid returns 2 tiles
#: and the scan returns 3, and the equality below fails.
_LEVEL: list[SimpleNamespace] = [
    _tile(pygame.FRect(140, 190, 48, 32)),  # floor, directly underfoot
    _tile(pygame.FRect(182, 150, 32, 64)),  # wall, overlapping the body
    # Neighbouring cell (0,1): outside the body, inside SEARCH_INFLATE so the
    # scan finds it, and inside the *margin-inflated* query so only the grid
    # needs the margin to reach it.
    _tile(pygame.FRect(4, 132, 32, 32)),
    _tile(pygame.FRect(2000, 2000, 64, 64)),  # far away: never a candidate
]

#: A body wholly inside cell (1,1) — which is what makes the margin matter.
_BODY = pygame.FRect(140, 140, 48, 56)


def _grid_for(tiles: list[SimpleNamespace]) -> SpatialHash:
    grid = SpatialHash(cell_size=128)
    grid.add_all(tiles)
    return grid


def _both_paths(box: pygame.FRect) -> tuple[list[object], list[object]]:
    """The grid's answer and the scan's answer, for the same query.

    Compared as sets, and the difference is worth stating: the grid returns
    members in *cell* order while the scan returns them in *insertion* order,
    so the two lists are equal only when a level happens to lay out in that
    order. The candidate set is what the physics consumes — ``resolve_collisions``
    tests every candidate and resolves each axis independently — so set equality
    is the contract that has to hold. Pinning the order would pin an accident of
    the current terrain layout instead.
    """
    with_grid = get_nearby_sprites(_prober(box), spatial_hash=_grid_for(_LEVEL))
    without_grid = get_nearby_sprites(_prober(box), spatial_hash=None, collision_sprites=_LEVEL)
    return with_grid, without_grid


def test_the_grid_and_the_scan_return_the_same_terrain() -> None:
    """The contract: wired is faster, unwired is slower, both are identical.

    Measured on the shipped level, dropping the grid costs x2.4 on the whole
    simulation (14.23ms -> 5.40ms per tick at 60 enemies). That is worth
    having, and it is only safe because the two paths agree.
    """
    with_grid, without_grid = _both_paths(_BODY)

    assert {id(sprite) for sprite in with_grid} == {id(sprite) for sprite in without_grid}


def test_parity_still_holds_for_a_tile_reachable_only_through_the_margin() -> None:
    """The query margin is load-bearing, and parity must cover it.

    ``QUERY_MARGIN_PX`` exists so a body resting exactly on a surface, or
    reached within one tick of movement, is still found. Deleting it does not
    raise: it makes the grid quietly *miss* tiles the scan returns, which is
    the worst shape this code could break in. This fixture places a tile just
    outside the hitbox, so the parity assertion below is decided by the margin
    alone.
    """
    margin_only_tile = _LEVEL[2]
    with_grid, without_grid = _both_paths(_BODY)

    assert not margin_only_tile.hitbox.colliderect(_BODY)  # the setup holds
    assert margin_only_tile in with_grid
    assert margin_only_tile in without_grid
    assert {id(sprite) for sprite in with_grid} == {id(sprite) for sprite in without_grid}


def test_both_paths_see_the_same_terrain_when_moved_onto_a_cell_boundary() -> None:
    """Parity must survive the awkward case: an entity straddling two cells.

    A query box spanning several cells is exactly where a bucketing bug would
    show up as a *missed* tile, and a missed tile is a sprite that falls
    through the floor.
    """
    box = pygame.FRect(150, 140, 48, 56)  # crosses the x=192-ish cell seam

    with_grid, without_grid = _both_paths(box)

    assert {id(sprite) for sprite in with_grid} == {id(sprite) for sprite in without_grid}
    assert with_grid  # and neither answer may be trivially empty


def test_the_far_tile_is_excluded_by_both_paths() -> None:
    """Parity must not be reached by both paths being uniformly wrong.

    Without this, a bug that made the grid return everything would still pass
    the equality above on a level where every tile happens to be near.
    """
    far_away = _LEVEL[-1]

    with_grid, without_grid = _both_paths(_BODY)

    assert far_away not in with_grid
    assert far_away not in without_grid
    assert _LEVEL[0] in with_grid  # the floor is reachable from both


def test_the_fallback_answers_are_not_accidentally_empty() -> None:
    """Guard the fixture itself: parity over two empty lists proves nothing."""
    box = pygame.FRect(100, 160, 48, 56)

    without_grid = get_nearby_sprites(_prober(box), spatial_hash=None, collision_sprites=_LEVEL)

    assert len(without_grid) == 3  # everything but the far tile


def test_get_nearby_sprites_with_spatial_hash() -> None:
    """SpatialHash path returns sprites near the entity."""
    entity = SimpleNamespace(
        hitbox=pygame.FRect(100, 100, 48, 56),
        old_hitbox=pygame.FRect(100, 100, 48, 56),
        velocity=pygame.Vector2(0, 0),
        on_surface={"floor": False, "left": False, "right": False},
        collision_sprites=[],
        spatial_hash=None,
        normal_gravity=2000.0,
        max_fall_speed=1500.0,
        drag_coefficient=0.08,
        fall_drag_coefficient=0.12,
        is_wall_sliding=lambda: False,
    )

    grid = SpatialHash(cell_size=64)
    tile_a = _tile(pygame.FRect(100, 100, 32, 32))
    tile_b = _tile(pygame.FRect(500, 500, 32, 32))
    grid.add(tile_a)
    grid.add(tile_b)

    nearby = get_nearby_sprites(entity, spatial_hash=grid)
    assert tile_a in nearby
    assert tile_b not in nearby


def test_get_nearby_sprites_no_spatial_hash_returns_empty() -> None:
    entity = SimpleNamespace(
        hitbox=pygame.FRect(0, 0, 48, 56),
    )
    nearby = get_nearby_sprites(entity, spatial_hash=None, collision_sprites=None)
    assert nearby == []


def test_update_contact_state_breaks_early_when_all_flags_set() -> None:
    """Once floor + both walls are set, the loop breaks early."""
    # Entity hitbox: FRect(50, 190, 48, 56)
    # Floor probe: bottomleft=(50, 246), (48, 2) -> y range 246..248
    # Left probe: (48, 204), (2, 28) -> x range 48..50
    # Right probe: (98, 204), (2, 28) -> x range 98..100
    entity = _ContactEntity(pygame.FRect(50, 190, 48, 56))
    floor_tile = _tile(pygame.FRect(0, 246, 200, 32))
    left_tile = _tile(pygame.FRect(46, 204, 8, 28))
    right_tile = _tile(pygame.FRect(96, 204, 8, 28))
    update_contact_state(entity, [floor_tile, left_tile, right_tile])
    assert entity.on_surface["floor"] is True
    assert entity.on_surface["left"] is True
    assert entity.on_surface["right"] is True
