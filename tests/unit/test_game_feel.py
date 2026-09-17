"""Game-feel assists: jump cut, ground snap, step-up, corner correction."""

import pygame
import pytest

from src.core.settings import GameFeel
from src.physics.movement import apply_jump_cut, move_entity, resolve_jump


class FeelEntity:
    """Minimal entity for feel helpers (velocity + jump timers)."""

    def __init__(self) -> None:
        self.velocity = pygame.math.Vector2(0, 0)
        self.jump_buffer_timer = 0.0
        self.coyote_timer = 0.0
        self.jump_height = 750.0
        self.wall_jump_height = 700.0
        self.wall_jump_push_multiplier = 1.0
        self.wall_jump_lock_timer = 0.0
        self.wall_jump_lock_duration = 0.2
        self.wall_jump_min_lock = 0.05
        self.wall_jumps_left = 1
        self.midair_jumps_left = 0
        self.speed = 450.0
        self.move_axis = 0.0
        self.on_surface = {"floor": False, "left": False, "right": False}


class WallEntity(FeelEntity):
    """Feel entity with collision geometry for resolve/move tests."""

    def __init__(self, hitbox: pygame.FRect) -> None:
        super().__init__()
        self.rect = hitbox.copy()
        self.hitbox = hitbox
        self.old_hitbox = hitbox.copy()
        self.collision_sprites: list = []
        self.floor_contacts = 0
        self.wall_contacts = 0
        # MovementComponent-owned kinematics live on the entity here.
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
        self.floor_contacts += 1

    def _on_wall_contact(self) -> None:
        self.wall_contacts += 1


def _tile(box: pygame.FRect):
    from types import SimpleNamespace

    return SimpleNamespace(rect=box, hitbox=box.copy(), old_hitbox=box.copy())


def test_jump_cut_cuts_the_rise_by_default() -> None:
    entity = FeelEntity()
    entity.velocity.y = -600.0
    apply_jump_cut(entity)
    assert entity.velocity.y == -240.0  # -600 / JUMP_CUT_DIVISOR


def test_jump_cut_neutral_at_divisor_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GameFeel, "JUMP_CUT_DIVISOR", 1.0)
    entity = FeelEntity()
    entity.velocity.y = -600.0
    apply_jump_cut(entity, GameFeel.JUMP_CUT_DIVISOR)
    assert entity.velocity.y == -600.0


def test_jump_cut_halves_rise_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GameFeel, "JUMP_CUT_DIVISOR", 2.0)
    entity = FeelEntity()
    entity.velocity.y = -600.0
    apply_jump_cut(entity, GameFeel.JUMP_CUT_DIVISOR)
    assert entity.velocity.y == -300.0


def test_jump_cut_ignores_falling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GameFeel, "JUMP_CUT_DIVISOR", 2.0)
    entity = FeelEntity()
    entity.velocity.y = 400.0
    apply_jump_cut(entity, GameFeel.JUMP_CUT_DIVISOR)
    assert entity.velocity.y == 400.0


def test_resolve_jump_still_launches() -> None:
    entity = FeelEntity()
    entity.jump_buffer_timer = 0.1
    entity.coyote_timer = 0.1
    resolve_jump(entity)
    assert entity.velocity.y == -entity.jump_height


def test_ground_snap_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GameFeel, "GROUND_SNAP_PX", 0.0)
    entity = WallEntity(pygame.FRect(50, 140, 40, 48))
    entity.velocity.y = 100.0
    floor = _tile(pygame.FRect(0, 191, 400, 64))  # 3 px gap, unreachable this tick
    entity.collision_sprites = [floor]

    move_entity(entity, 1 / 60)

    assert entity.hitbox.bottom < 191.0  # still falling


def test_ground_snap_sticks_to_close_floor_by_default() -> None:
    entity = WallEntity(pygame.FRect(50, 140, 40, 48))
    entity.velocity.y = 100.0
    floor = _tile(pygame.FRect(0, 191, 400, 64))  # 3 px gap
    entity.collision_sprites = [floor]

    move_entity(entity, 1 / 60)

    assert entity.hitbox.bottom == pytest.approx(191.0)
    assert entity.velocity.y == 0.0


def test_step_up_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.physics.collisions import resolve_collisions

    monkeypatch.setattr(GameFeel, "STEP_UP_PX", 0.0)
    entity = WallEntity(pygame.FRect(60, 152, 40, 48))  # feet at 200
    entity.old_hitbox = entity.hitbox.copy()
    entity.on_surface["floor"] = True
    entity.velocity.x = 300.0
    ledge = _tile(pygame.FRect(90, 194, 32, 200))  # 6 px ledge

    resolve_collisions(entity, "horizontal", [ledge])

    assert entity.hitbox.right == pytest.approx(90.0)
    assert entity.velocity.x == 0.0


def test_step_up_mounts_small_ledge_by_default() -> None:
    from src.physics.collisions import resolve_collisions

    entity = WallEntity(pygame.FRect(60, 152, 40, 48))
    entity.old_hitbox = entity.hitbox.copy()
    entity.on_surface["floor"] = True
    entity.velocity.x = 300.0
    ledge = _tile(pygame.FRect(90, 194, 32, 200))

    resolve_collisions(entity, "horizontal", [ledge])

    assert entity.hitbox.bottom == pytest.approx(194.0)
    assert entity.velocity.x == 300.0


def test_corner_correction_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.physics.collisions import resolve_collisions

    monkeypatch.setattr(GameFeel, "CORNER_CORRECT_PX", 0.0)
    entity = WallEntity(pygame.FRect(90, 120, 40, 48))
    entity.old_hitbox = entity.hitbox.copy()
    entity.velocity.y = -500.0
    entity.move_axis = 1.0
    ceiling = _tile(pygame.FRect(0, 100, 100, 32))  # right edge at x=100

    resolve_collisions(entity, "vertical", [ceiling])

    assert entity.hitbox.top == pytest.approx(132.0)
    assert entity.velocity.y == 0.0


def test_corner_correction_nudges_past_the_edge_by_default() -> None:
    from src.physics.collisions import resolve_collisions

    entity = WallEntity(pygame.FRect(90, 120, 40, 48))
    entity.old_hitbox = entity.hitbox.copy()
    entity.velocity.y = -500.0
    entity.move_axis = 1.0
    ceiling = _tile(pygame.FRect(0, 100, 100, 32))

    resolve_collisions(entity, "vertical", [ceiling])

    assert entity.hitbox.x == pytest.approx(102.0)
    assert entity.velocity.y == -500.0
