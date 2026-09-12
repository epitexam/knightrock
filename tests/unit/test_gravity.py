"""Tests for apply_entity_gravity (physics/gravity)."""

from types import SimpleNamespace

import pygame
import pytest

from src.physics.gravity import apply_entity_gravity


def make_entity(**overrides) -> SimpleNamespace:
    """Build a minimal entity matching the gravity protocol."""
    defaults = dict(
        velocity=pygame.Vector2(0, 0),
        on_surface={"floor": False, "left": False, "right": False},
        normal_gravity=2000.0,
        fall_gravity=2800.0,
        slide_gravity=300.0,
        max_slide_speed=80.0,
        max_fall_speed=1500.0,
        drag_coefficient=0.08,
        fall_drag_coefficient=0.12,
        is_wall_sliding=lambda: False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_normal_gravity_applied_when_falling_from_rest() -> None:
    entity = make_entity(velocity=pygame.Vector2(0, 0))
    apply_entity_gravity(entity, 1 / 60)
    assert entity.velocity.y == pytest.approx(2000.0 * (1 / 60))


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