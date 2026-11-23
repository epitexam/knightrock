"""Projectile dense rows mirror the pooled sprites until promotion."""

import os
from dataclasses import replace

import pygame
import pytest

from src.entities.shots import SHOTS
from tests.headless.arena import DT, arena, settle


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


CONFIG = replace(SHOTS["bolt"].config, lifetime=5.0)


def test_spawn_registers_a_generation_checked_row() -> None:
    level, _pad, _player = arena()
    settle(level)
    system = level.projectile_system
    first = system.spawn(CONFIG, (100.0, 200.0), (0.0, 0.0), "player")
    second = system.spawn(CONFIG, (140.0, 200.0), (0.0, 0.0), "player")

    assert len(system.table) == 2
    handle = system.table.handle_of(system._slot_of_proxy[id(first)])
    other = system.table.handle_of(system._slot_of_proxy[id(second)])
    assert handle != other
    assert handle[1] == other[1] == 0


def test_every_tick_writes_and_checks_the_mirror() -> None:
    level, _pad, _player = arena()
    settle(level)
    system = level.projectile_system
    system.spawn(CONFIG, (100.0, 200.0), (140.0, -30.0), "player")

    for _ in range(30):
        level.update(DT)
        assert len(system.table) == 1
        slot = system._slot_of_proxy[id(next(iter(level.groups.projectile_sprites)))]
        system.table.assert_mirror(slot)


def test_a_recycled_pool_object_gets_a_new_generation() -> None:
    level, _pad, _player = arena()
    settle(level)
    system = level.projectile_system
    first = system.spawn(CONFIG, (100.0, 200.0), (0.0, 0.0), "player")
    old_handle = system.table.handle_of(system._slot_of_proxy[id(first)])

    first.life = 0.0
    level.update(DT)
    assert len(system.table) == 0

    second = system.spawn(CONFIG, (200.0, 200.0), (0.0, 0.0), "player")
    assert second is first
    new_handle = system.table.handle_of(system._slot_of_proxy[id(second)])
    assert new_handle[0] == old_handle[0]
    assert new_handle[1] == old_handle[1] + 1
    assert system.table.slot_of(old_handle) is None


def test_a_rewind_restores_the_generation_checked_handle() -> None:
    level, _pad, _player = arena()
    settle(level)
    system = level.projectile_system
    shot = system.spawn(CONFIG, (100.0, 200.0), (140.0, 0.0), "player")
    level.update(DT)
    snapshot = level.save_state()
    captured_handle = snapshot.projectiles[0].handle

    shot.life = 0.0
    level.update(DT)
    assert len(system.table) == 0

    level.load_state(snapshot)
    assert len(system.table) == 1
    assert system.handle_for(shot) == captured_handle
    slot = system._slot_of_proxy[id(shot)]
    system.table.assert_mirror(slot)
