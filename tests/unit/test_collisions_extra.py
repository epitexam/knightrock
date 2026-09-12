"""Additional tests for physics/collisions: update_contact_state and spatial hash path."""

from types import SimpleNamespace

import pygame
import pytest

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