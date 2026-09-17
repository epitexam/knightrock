"""Collision robustness: slide-on-graze, bounded resolve, crush, sticky carry."""

import pygame
import pytest

from src.core.settings import Collision, PlatformRide
from src.physics.collisions import resolve_collisions
from src.physics.movement import _revert_carry_crush, apply_moving_platform, move_entity


class RobustEntity:
    """Collision entity with crush/carry bookkeeping like the real one."""

    def __init__(self, hitbox: pygame.FRect) -> None:
        self.rect = hitbox.copy()
        self.hitbox = hitbox
        self.old_hitbox = hitbox.copy()
        self.velocity = pygame.math.Vector2(0, 0)
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.collision_sprites: list = []
        self.crushed = False
        self.carry_backup = None
        self.move_axis = 0.0
        self.normal_gravity = 2000.0
        self.fall_gravity = 2800.0
        self.slide_gravity = 300.0
        self.max_slide_speed = 80.0
        self.max_fall_speed = 1500.0
        self.drag_coefficient = 0.08
        self.fall_drag_coefficient = 0.12
        self.gravity_scale = 1.0
        self.spatial_hash = None

    def sync_rects(self) -> None:
        self.rect.midbottom = self.hitbox.midbottom

    def is_wall_sliding(self) -> bool:
        return False

    def check_contact(self) -> None:
        pass

    def _on_floor_contact(self) -> None:
        pass

    def _on_wall_contact(self) -> None:
        pass


def _tile(box: pygame.FRect):
    from types import SimpleNamespace

    return SimpleNamespace(rect=box, hitbox=box.copy(), old_hitbox=box.copy())


def test_wall_graze_stops_by_default() -> None:
    entity = RobustEntity(pygame.FRect(62, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(60, 150, 40, 48)
    entity.velocity.x = 500.0
    wall = _tile(pygame.FRect(100, 100, 32, 200))

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.right == pytest.approx(100.0)
    assert entity.velocity.x == 0.0


def test_wall_graze_slides_when_threshold_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Collision, "MIN_PENETRATION_PX", 4.0)
    entity = RobustEntity(pygame.FRect(62, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(60, 150, 40, 48)
    entity.velocity.x = 500.0
    wall = _tile(pygame.FRect(100, 100, 32, 200))

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.right == pytest.approx(100.0)  # still pushed out
    assert entity.velocity.x == 500.0  # but momentum kept: slides


def test_shallow_graze_keeps_momentum_by_default() -> None:
    entity = RobustEntity(pygame.FRect(60.5, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(60, 150, 40, 48)  # right edge at the wall line
    entity.velocity.x = 500.0
    wall = _tile(pygame.FRect(100, 100, 32, 200))

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.right == pytest.approx(100.0)  # pushed out
    assert entity.velocity.x == 500.0  # 0.5 px graze: slides instead of stopping


def test_deep_overlap_teleports_when_unbounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Collision, "MAX_RESOLVE_PX", float("inf"))
    entity = RobustEntity(pygame.FRect(105, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(105, 150, 40, 48)
    wall = _tile(pygame.FRect(100, 100, 32, 200))

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.left == pytest.approx(132.0)  # legacy full teleport
    assert entity.crushed is False


def test_deep_overlap_clamps_and_flags_crush_by_default() -> None:
    entity = RobustEntity(pygame.FRect(105, 150, 40, 48))
    entity.old_hitbox = pygame.FRect(105, 150, 40, 48)
    wall = _tile(pygame.FRect(100, 100, 32, 200))

    resolve_collisions(entity, "horizontal", [wall])

    assert entity.hitbox.left == pytest.approx(121.0)  # 105 + capped 16
    assert entity.crushed is True


def test_carry_crush_reverts_to_pre_carry_position() -> None:
    entity = RobustEntity(pygame.FRect(50, 100, 40, 48))
    entity.velocity = pygame.math.Vector2(200, 100)
    entity.crushed = True
    entity.carry_backup = (50.0, 100.0, 40.0, 48.0)
    entity.hitbox = pygame.FRect(70, 130, 40, 48)

    _revert_carry_crush(entity)

    assert (entity.hitbox.x, entity.hitbox.y) == pytest.approx((50.0, 100.0))
    assert entity.velocity.x == 0.0
    assert entity.velocity.y == 0.0
    assert entity.carry_backup is None


def test_revert_is_noop_without_crush() -> None:
    entity = RobustEntity(pygame.FRect(70, 130, 40, 48))
    entity.carry_backup = (50.0, 100.0, 40.0, 48.0)

    _revert_carry_crush(entity)

    assert (entity.hitbox.x, entity.hitbox.y) == pytest.approx((70.0, 130.0))


def test_carry_stores_backup_for_crush_recovery() -> None:
    entity = RobustEntity(pygame.FRect(50, 142, 40, 48))
    entity.old_hitbox = entity.hitbox.copy()
    entity.on_surface["floor"] = True
    platform = _tile(pygame.FRect(40, 200, 120, 16))
    platform.old_hitbox = pygame.FRect(40, 190, 120, 16)  # moved down 10

    apply_moving_platform(entity, [platform])

    assert entity.carry_backup == (50.0, 142.0, 40.0, 48.0)
    assert entity.hitbox.y == pytest.approx(152.0)


def test_fast_descending_platform_detaches_when_sticky_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PlatformRide, "STICKY_FACTOR", 0.0)
    entity = RobustEntity(pygame.FRect(50, 158, 40, 48))  # 10 px under old top
    entity.old_hitbox = entity.hitbox.copy()
    entity.on_surface["floor"] = True
    platform = _tile(pygame.FRect(40, 216, 120, 16))
    platform.old_hitbox = pygame.FRect(40, 196, 120, 16)  # dropped 20

    apply_moving_platform(entity, [platform])

    assert entity.hitbox.y == pytest.approx(158.0)  # left behind


def test_sticky_carry_follows_fast_descent_by_default() -> None:
    entity = RobustEntity(pygame.FRect(50, 158, 40, 48))  # 10 px under old top
    entity.old_hitbox = entity.hitbox.copy()
    entity.on_surface["floor"] = True
    platform = _tile(pygame.FRect(40, 216, 120, 16))
    platform.old_hitbox = pygame.FRect(40, 196, 120, 16)  # dropped 20

    apply_moving_platform(entity, [platform])

    assert entity.hitbox.bottom == pytest.approx(216.0)  # landed on the new top


def test_full_move_resets_crush_flag() -> None:
    entity = RobustEntity(pygame.FRect(50, 100, 40, 48))
    entity.crushed = True
    entity.velocity = pygame.math.Vector2(0, 0)
    entity.collision_sprites = []

    move_entity(entity, 1 / 60)

    assert entity.crushed is False
