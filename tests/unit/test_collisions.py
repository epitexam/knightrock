"""Tests des résolutions de collision (physics/collisions)."""

from types import SimpleNamespace

import pygame
import pytest

from src.physics.collisions import get_nearby_sprites, hitbox_collide, resolve_collisions


class StubEntity:
    """Entité minimale compatible CollisionEntity."""

    def __init__(self, hitbox: pygame.FRect) -> None:
        self.rect = hitbox.copy()
        self.hitbox = hitbox
        self.old_hitbox = hitbox.copy()
        self.velocity = pygame.math.Vector2(0, 0)
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.collision_sprites = []
        self.floor_contacts = 0
        self.wall_contacts = 0

    def sync_rects(self) -> None:
        self.rect.midbottom = self.hitbox.midbottom

    def _on_floor_contact(self) -> None:
        self.floor_contacts += 1

    def _on_wall_contact(self) -> None:
        self.wall_contacts += 1


@pytest.fixture()
def floor_tile() -> SimpleNamespace:
    return SimpleNamespace(
        rect=pygame.FRect(0, 200, 400, 64),
        hitbox=pygame.FRect(0, 200, 400, 64),
        old_hitbox=pygame.FRect(0, 200, 400, 64),
    )


def test_hitbox_collide_compares_hitboxes() -> None:
    a = SimpleNamespace(rect=pygame.FRect(0, 0, 10, 10), hitbox=pygame.FRect(0, 0, 10, 10))
    b = SimpleNamespace(rect=pygame.FRect(5, 5, 10, 10), hitbox=pygame.FRect(5, 5, 10, 10))
    far = SimpleNamespace(rect=pygame.FRect(500, 500, 10, 10), hitbox=pygame.FRect(500, 500, 10, 10))

    assert hitbox_collide(a, b)
    assert not hitbox_collide(a, far)


def test_vertical_landing_snaps_to_the_tile_top(floor_tile) -> None:
    entity = StubEntity(pygame.FRect(50, 190, 48, 56))
    entity.old_hitbox = pygame.FRect(50, 180, 48, 56)
    entity.velocity.y = 500.0

    resolve_collisions(entity, "vertical", [floor_tile])

    assert entity.hitbox.bottom == pytest.approx(floor_tile.hitbox.top)
    assert entity.velocity.y == 0.0


def test_ceiling_bump_snaps_to_the_tile_bottom(floor_tile) -> None:
    entity = StubEntity(pygame.FRect(50, 230, 48, 56))
    entity.old_hitbox = pygame.FRect(50, 240, 48, 56)
    entity.velocity.y = -500.0

    resolve_collisions(entity, "vertical", [floor_tile])

    assert entity.hitbox.top == pytest.approx(floor_tile.hitbox.bottom)
    assert entity.velocity.y == 0.0


def test_horizontal_run_into_wall_stops_at_its_edge() -> None:
    wall = SimpleNamespace(
        rect=pygame.FRect(100, 100, 32, 200),
        hitbox=pygame.FRect(100, 100, 32, 200),
        old_hitbox=pygame.FRect(100, 100, 32, 200),
    )
    entity = StubEntity(pygame.FRect(70, 150, 48, 56))
    entity.old_hitbox = pygame.FRect(60, 150, 48, 56)
    entity.velocity.x = 400.0

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.right == pytest.approx(wall.hitbox.left)
    assert entity.velocity.x == 0.0


def test_get_nearby_sprites_falls_back_to_linear_search() -> None:
    entity = StubEntity(pygame.FRect(0, 0, 48, 56))
    near = SimpleNamespace(rect=pygame.FRect(10, 10, 64, 64), hitbox=pygame.FRect(10, 10, 64, 64))
    far = SimpleNamespace(rect=pygame.FRect(5000, 5000, 64, 64), hitbox=pygame.FRect(5000, 5000, 64, 64))
    entity.collision_sprites = [near, far]

    nearby = get_nearby_sprites(entity, collision_sprites=entity.collision_sprites)

    assert near in nearby
    assert far not in nearby