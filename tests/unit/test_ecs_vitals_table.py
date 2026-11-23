"""Vitals values live in dense rows while the rules stay in the component."""

import os

import pygame
import pytest

from src.entities.vitals import Vitals
from tests.headless.arena import arena, settle


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_writes_reach_the_row_and_the_component_mirror() -> None:
    level, _pad, player = arena()
    settle(level)
    vitals = player.vitals
    slot = vitals._slot
    assert slot is not None
    table = level.vitals_table

    player.stagger_timer = 0.25
    player.super_armor = True
    player.health = 42.0

    assert table.column("stagger_timer")[slot] == pytest.approx(0.25)
    assert table.column("super_armor")[slot] is True
    assert table.column("health")[slot] == 42.0
    table.assert_mirror(slot)


def test_a_standalone_vitals_still_works_without_a_table() -> None:
    vitals = Vitals(health=30.0, max_health=50.0)
    vitals.stagger_timer = 0.3
    vitals.apply_damage(5.0)

    assert vitals.health == 25.0
    assert vitals.stagger_timer == 0.3
    assert vitals._table is None


def test_a_rewind_restores_the_vitals_row() -> None:
    level, _pad, player = arena()
    settle(level)
    snapshot = level.save_state()
    player.stagger_timer = 0.7
    player.health = 1.0
    level.load_state(snapshot)

    slot = player.vitals._slot
    assert slot is not None
    level.vitals_table.assert_mirror(slot)
    assert player.health == snapshot.entities[player.id].vitals.health
