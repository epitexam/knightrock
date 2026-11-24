"""Kinematic views keep the mutation spelling while the columns own the values."""

import os

import pygame
import pytest
from pygame.math import Vector2

from tests.headless.arena import arena, settle


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_in_place_writes_reach_the_dense_row_and_the_component() -> None:
    level, _pad, player = arena()
    settle(level)
    slot = player.movement_slot
    assert slot is not None
    table = level.movement_table

    player.velocity.x = 123.0
    player.velocity.y = -7.0
    player.on_surface["floor"] = True

    assert table.column("vx")[slot] == 123.0
    assert table.column("vy")[slot] == -7.0
    assert table.column("floor")[slot] is True


def test_whole_object_assignment_goes_through_the_view() -> None:
    level, _pad, player = arena()
    settle(level)
    slot = player.movement_slot
    assert slot is not None

    player.velocity = Vector2(9.0, -4.0)
    player.on_surface = {"floor": False, "left": True, "right": False}

    assert Vector2(player.velocity) == Vector2(9.0, -4.0)
    assert level.movement_table.column("vx")[slot] == 9.0
    assert level.movement_table.column("left")[slot] is True


def test_a_rewind_restores_the_columns_through_the_entity_view() -> None:
    level, _pad, player = arena()
    settle(level)
    slot = player.movement_slot
    assert slot is not None
    snapshot = level.save_state()

    player.velocity.x = 500.0
    player.on_surface["floor"] = not player.on_surface["floor"]
    level.load_state(snapshot)

    assert level.movement_table.column("vx")[slot] == snapshot.entities[player.id].velocity[0]
    assert player.movement_slot == slot
    assert player._movement.velocity.x == snapshot.entities[player.id].velocity[0]
