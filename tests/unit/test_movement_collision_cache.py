"""PERF-01: nearby collision sprites are resolved once per move_entity call."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
from pygame.math import Vector2

from src.physics.movement import move_entity


def make_entity() -> SimpleNamespace:
    return SimpleNamespace(
        velocity=Vector2(2000.0, -2000.0),
        hitbox=pygame.FRect(0, 0, 40, 40),
        old_hitbox=pygame.FRect(0, 0, 40, 40),
        on_surface={"floor": False, "left": False, "right": False},
        collision_sprites=[],
        normal_gravity=2000.0,
        fall_gravity=2800.0,
        slide_gravity=300.0,
        max_slide_speed=80.0,
        max_fall_speed=1500.0,
        drag_coefficient=0.08,
        fall_drag_coefficient=0.12,
        is_wall_sliding=lambda: False,
        sync_rects=Mock(),
        _on_floor_contact=Mock(),
        _on_wall_contact=Mock(),
    )


def test_move_entity_queries_nearby_sprites_once(monkeypatch) -> None:
    entity = make_entity()
    query_count = {"value": 0}

    def counting_get_nearby(sprite, collision_sprites):
        query_count["value"] += 1
        return []

    monkeypatch.setattr(
        "src.physics.movement.get_nearby_sprites", counting_get_nearby)

    move_entity(entity, 1 / 60)  # type: ignore[arg-type]

    # One query per move; NOT one per substep (velocity above forces several
    # horizontal and vertical substeps) nor an extra pass for contact state.
    assert query_count["value"] == 1
    entity.sync_rects.assert_called()


def test_move_entity_keeps_contact_state_consistent() -> None:
    entity = make_entity()
    entity.velocity = Vector2(0.0, 0.0)

    move_entity(entity, 1 / 60)  # type: ignore[arg-type]

    assert entity.on_surface == {"floor": False, "left": False, "right": False}
    entity._on_floor_contact.assert_not_called()
    entity._on_wall_contact.assert_not_called()