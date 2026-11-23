"""The pushbox in the dense row is the same object the simulation mutates."""

import os

import pygame
import pytest

from tests.headless.arena import arena, settle


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_mutation_reaches_the_table_owned_rect() -> None:
    level, _pad, player = arena()
    settle(level)
    slot = player.geometry_slot
    assert slot is not None
    table = level.geometry_table

    box = player.hitbox
    assert box is table.hitbox_of(slot)
    box.center = (321.0, 456.0)

    assert table.hitbox_of(slot).center == (321.0, 456.0)
    assert player._pushbox is box


def test_rebinding_the_collider_updates_the_row() -> None:
    level, _pad, player = arena()
    settle(level)
    slot = player.geometry_slot
    assert slot is not None

    replacement = pygame.FRect(10.0, 20.0, 30.0, 40.0)
    player.hitbox = replacement

    assert level.geometry_table.hitbox_of(slot) is replacement
    assert player.hitbox is replacement


def test_a_rewind_keeps_the_row_bound_to_the_entity() -> None:
    level, _pad, player = arena()
    settle(level)
    snapshot = level.save_state()
    slot = player.geometry_slot

    player.hitbox.x += 250.0
    level.load_state(snapshot)

    assert player.geometry_slot == slot
    assert level.geometry_table.hitbox_of(slot) is player.hitbox
    assert player.hitbox.x == pytest.approx(snapshot.entities[player.id].hitbox[0])
