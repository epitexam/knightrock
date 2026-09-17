"""Tests for apply_entity_gravity (physics/gravity)."""

from types import SimpleNamespace

import pygame
import pytest

from src.core.settings import GameFeel
from src.physics.gravity import apply_entity_gravity


def make_entity(**overrides) -> SimpleNamespace:
    """Build a minimal entity matching the gravity protocol."""
    defaults = {
        "velocity": pygame.Vector2(0, 0),
        "on_surface": {"floor": False, "left": False, "right": False},
        "normal_gravity": 2000.0,
        "fall_gravity": 2800.0,
        "slide_gravity": 300.0,
        "max_slide_speed": 80.0,
        "max_fall_speed": 1500.0,
        "drag_coefficient": 0.08,
        "fall_drag_coefficient": 0.12,
        "gravity_scale": 1.0,
        "fast_fall": False,
        "is_wall_sliding": lambda: False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_normal_gravity_applied_when_falling_from_rest(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy fall curve (apex hang disabled)."""
    monkeypatch.setattr(GameFeel, "APEX_GRAVITY_DIVISOR", 1.0)
    entity = make_entity(velocity=pygame.Vector2(0, 0))
    apply_entity_gravity(entity, 1 / 60)
    assert entity.velocity.y == pytest.approx(2000.0 * (1 / 60))


def test_rest_start_still_entering_the_apex_band(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the apex hang enabled, v=0 divides gravity (engaged by default)."""
    entity = make_entity(velocity=pygame.Vector2(0, 0))
    apply_entity_gravity(entity, 1 / 60)
    expected = 0.0 + (2000.0 / GameFeel.APEX_GRAVITY_DIVISOR) * (1 / 60)
    assert entity.velocity.y == pytest.approx(expected)


def test_fall_gravity_used_when_velocity_positive() -> None:
    entity = make_entity(velocity=pygame.Vector2(0, 500.0))
    before = entity.velocity.y
    apply_entity_gravity(entity, 1 / 60)
    assert entity.velocity.y > before


def test_drag_slows_descent() -> None:
    entity = make_entity(velocity=pygame.Vector2(0, 800.0))
    apply_entity_gravity(entity, 1 / 60)
    raw_increase = 2800.0 * (1 / 60)
    actual_increase = entity.velocity.y - 800.0
    assert actual_increase < raw_increase


def test_max_fall_speed_is_clamped() -> None:
    entity = make_entity(velocity=pygame.Vector2(0, 1400.0))
    for _ in range(60):
        apply_entity_gravity(entity, 1 / 60)
    assert entity.velocity.y <= 1500.0 + 0.1


def test_wall_slide_uses_slide_gravity() -> None:
    """Wall slide applies slide_gravity but clamps to max_slide_speed."""
    entity = make_entity(
        velocity=pygame.Vector2(0, 0.0),
        is_wall_sliding=lambda: True,
    )
    apply_entity_gravity(entity, 1 / 60)
    # 0 + 300 * dt = 5.0, which is below max_slide_speed (80.0)
    assert entity.velocity.y == pytest.approx(300.0 * (1 / 60))


def test_wall_slide_clamps_to_max_slide_speed() -> None:
    entity = make_entity(
        velocity=pygame.Vector2(0, 300.0),
        is_wall_sliding=lambda: True,
    )
    for _ in range(60):
        apply_entity_gravity(entity, 1 / 60)
    assert entity.velocity.y <= 80.0 + 0.1


def test_terminal_velocity_with_drag() -> None:
    entity = make_entity(velocity=pygame.Vector2(0, 0))
    for _ in range(120):
        apply_entity_gravity(entity, 1 / 60)
    assert entity.velocity.y <= 1500.0 + 0.5


def test_apex_hang_reduces_gravity_near_zero_vertical_speed() -> None:
    """|vy| below the apex threshold divides gravity by APEX_GRAVITY_DIVISOR."""
    entity = make_entity(velocity=pygame.Vector2(0, 50.0))
    apply_entity_gravity(entity, 1 / 60)
    expected = 50.0 + (2800.0 / GameFeel.APEX_GRAVITY_DIVISOR - 0.12 * 50.0) * (1 / 60)
    assert entity.velocity.y == pytest.approx(expected)


def test_apex_hang_does_not_apply_above_threshold() -> None:
    entity = make_entity(velocity=pygame.Vector2(0, 500.0))
    before = entity.velocity.y
    apply_entity_gravity(entity, 1 / 60)
    raw_increase = 2800.0 * (1 / 60)
    actual_increase = entity.velocity.y - before
    assert actual_increase == pytest.approx(raw_increase - 0.12 * 500.0 * (1 / 60))


def test_fast_fall_increases_falling_gravity() -> None:
    normal = make_entity(velocity=pygame.Vector2(0, 500.0))
    fast = make_entity(velocity=pygame.Vector2(0, 500.0), fast_fall=True)
    apply_entity_gravity(normal, 1 / 60)
    apply_entity_gravity(fast, 1 / 60)
    assert fast.velocity.y > normal.velocity.y
    # Both leave the apex band: the only difference is the multiplier.
    expected_fast = 500.0 + (2800.0 * GameFeel.FAST_FALL_GRAVITY_MULTIPLIER - 0.12 * 500.0) * (
        1 / 60
    )
    assert fast.velocity.y == pytest.approx(expected_fast)


def test_fast_fall_disabled_above_the_apex_band() -> None:
    """Fast fall never applies while still rising (apex branch wins)."""
    rising = make_entity(velocity=pygame.Vector2(0, -400.0), fast_fall=True)
    apply_entity_gravity(rising, 1 / 60)
    # Rising: normal gravity, no fast-fall multiplier.
    assert rising.velocity.y > -400.0
    assert rising.velocity.y < -400.0 + 2000.0 * (1 / 60) + 0.12 * 400.0 * (1 / 60) + 1e-6


def test_fast_fall_still_clamped_to_max_fall_speed() -> None:
    entity = make_entity(velocity=pygame.Vector2(0, 1400.0), fast_fall=True)
    for _ in range(60):
        apply_entity_gravity(entity, 1 / 60)
    assert entity.velocity.y <= 1500.0 + 0.1
