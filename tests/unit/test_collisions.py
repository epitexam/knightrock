"""Collision resolution tests (physics/collisions)."""

from types import SimpleNamespace

import pygame
import pytest

from src.simulation.physics.collisions import get_nearby_sprites, hitbox_collide, resolve_collisions
from src.simulation.settings import Combat


class StubEntity:
    """Minimal entity compatible with CollisionEntity."""

    def wall_bounce_factor(self) -> float:
        """The entity decides its own wall bounce, physics stays state-agnostic."""
        if self.state_machine.current_state_name == "knockback":
            return Combat.WALL_BOUNCE_FACTOR
        return 0.0

    def __init__(self, hitbox: pygame.FRect) -> None:
        self.rect = hitbox.copy()
        self.hitbox = hitbox
        self.old_hitbox = hitbox.copy()
        self.velocity = pygame.math.Vector2(0, 0)
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.collision_sprites = []
        self.move_axis = 0.0
        self.crushed = False
        self.state_machine = SimpleNamespace(current_state_name=None)
        self.floor_contacts = 0
        self.wall_contacts = 0

    def sync_rects(self) -> None:
        self.rect.midbottom = self.hitbox.midbottom

    def _on_floor_contact(self) -> None:
        self.floor_contacts += 1

    def _on_wall_contact(self) -> None:
        self.wall_contacts += 1


def test_a_collider_needs_no_state_machine_to_bounce_off_a_wall() -> None:
    """Physics asks the entity for a bounce factor, not for its state names."""
    entity = StubEntity(pygame.FRect(62, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(60, 150, 40, 48)
    entity.velocity.x = 100.0
    del entity.state_machine
    entity.wall_bounce_factor = lambda: 0.5  # type: ignore[method-assign]
    wall = SimpleNamespace(
        rect=pygame.FRect(100, 100, 32, 200),
        hitbox=pygame.FRect(100, 100, 32, 200),
        old_hitbox=pygame.FRect(100, 100, 32, 200),
    )

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.velocity.x == pytest.approx(-50.0)


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
    far = SimpleNamespace(
        rect=pygame.FRect(500, 500, 10, 10), hitbox=pygame.FRect(500, 500, 10, 10)
    )

    assert hitbox_collide(a, b)
    assert not hitbox_collide(a, far)


def test_vertical_landing_snaps_to_the_tile_top(floor_tile: SimpleNamespace) -> None:
    entity = StubEntity(pygame.FRect(50, 190, 48, 56))
    entity.old_hitbox = pygame.FRect(50, 144, 48, 56)  # was fully above
    entity.velocity.y = 500.0

    resolve_collisions(entity, "vertical", [floor_tile])

    assert entity.hitbox.bottom == pytest.approx(floor_tile.hitbox.top)
    assert entity.velocity.y == 0.0


def test_ceiling_bump_snaps_to_the_tile_bottom(floor_tile: SimpleNamespace) -> None:
    entity = StubEntity(pygame.FRect(50, 230, 48, 56))
    entity.old_hitbox = pygame.FRect(50, 264, 48, 56)  # was fully below
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
    entity.old_hitbox = pygame.FRect(40, 150, 48, 56)  # was fully left of the wall
    entity.velocity.x = 400.0

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.right == pytest.approx(wall.hitbox.left)
    assert entity.velocity.x == 0.0


def test_get_nearby_sprites_falls_back_to_linear_search() -> None:
    entity = StubEntity(pygame.FRect(0, 0, 48, 56))
    near = SimpleNamespace(rect=pygame.FRect(10, 10, 64, 64), hitbox=pygame.FRect(10, 10, 64, 64))
    far = SimpleNamespace(
        rect=pygame.FRect(5000, 5000, 64, 64), hitbox=pygame.FRect(5000, 5000, 64, 64)
    )
    entity.collision_sprites = [near, far]

    nearby = get_nearby_sprites(entity, collision_sprites=entity.collision_sprites)

    assert near in nearby
    assert far not in nearby
