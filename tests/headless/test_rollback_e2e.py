"""End-to-end determinism tests for the local rollback core (Phase 3 #3).

These tests prove the real invariant: *capturing a Level at tick K,
advancing the same Level through scripted inputs up to tick N, and then
rolling back to K and re-running the same script* must produce an
end-of-run state that is bit-identical to the end-of-run state of the
first forward pass.

A second group of tests covers the side-effects that only matter on a
real ``Level``: resurrecting entities that have been ``kill()``-ed and
reaping entities that were spawned after the target tick.
"""

from __future__ import annotations

import os

import pygame
import pytest

from src.core.level.level import Level
from src.entities.enemies.factory import create_enemy
from src.entities.entity import Entity


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


@pytest.fixture()
def scripted_level(build_level):
    """Level with rollback enabled; no enemy yet (caller decides)."""
    level = build_level()
    level.rollback_enabled = True
    # Enlarge the buffer so a 30-tick run stays fully rewindable.
    level.rollback = type(level.rollback)(capacity=64)
    return level


def _extract_entity_state(entity: Entity) -> dict[str, object]:
    """Comparable view of one entity's simulation-visible state."""
    return {
        "hitbox": (entity.hitbox.x, entity.hitbox.y, entity.hitbox.width, entity.hitbox.height),
        "velocity": (entity.velocity.x, entity.velocity.y),
        "on_surface": dict(entity.on_surface),
        "health": entity.health,
        "is_dead": entity.is_dead,
        "facing_right": entity.facing_right,
        "move_axis": entity.move_axis,
        "state": getattr(entity.state_machine, "current_state_name", None),
    }


def _script_tick(level: Level, inputs: dict[str, object]) -> None:
    for key, value in inputs.items():
        setattr(level.input_manager, key, value)
    level.update(1 / 60)


def _default_inputs() -> dict[str, object]:
    return {
        "move_axis": 0.0,
        "left_held": False,
        "right_held": False,
        "guard_held": False,
        "jump_just_pressed": False,
        "dash_just_pressed": False,
        "reset_just_pressed": False,
        "attack1_just_pressed": False,
        "attack2_just_pressed": False,
        "attack2_just_released": False,
        "attack3_just_pressed": False,
        "attack4_just_pressed": False,
        "special_attack_just_pressed": False,
    }


def test_rollback_replays_identical_state_from_same_inputs(build_level) -> None:
    level = build_level()
    level.rollback_enabled = True
    level.rollback = type(level.rollback)(capacity=64)

    script = [_default_inputs() for _ in range(20)]
    # Scripted motion so the state visibly changes between ticks.
    for t in range(3, 8):
        script[t]["move_axis"] = 1.0
    for t in range(10, 14):
        script[t]["move_axis"] = -1.0
    script[6]["jump_just_pressed"] = True
    script[15]["jump_just_pressed"] = True

    rollback_tick = 9

    # First forward pass — record state at `rollback_tick` and at the end.
    for _t, inputs in enumerate(script[: rollback_tick + 1]):
        _script_tick(level, inputs)
    state_at_rollback = {k: _extract_entity_state(level.player) for k in ("player",)}
    player_before = {k: dict(v) for k, v in state_at_rollback.items()}

    # Continue forward to the end of the script.
    for inputs in script[rollback_tick + 1 :]:
        _script_tick(level, inputs)
    end_state_first_pass = _extract_entity_state(level.player)

    # Roll back to `rollback_tick` and re-run the same remaining inputs.
    assert level.rollback.rollback_to(level, rollback_tick) is True
    assert _extract_entity_state(level.player) == player_before["player"]

    for inputs in script[rollback_tick + 1 :]:
        _script_tick(level, inputs)
    end_state_second_pass = _extract_entity_state(level.player)

    assert end_state_second_pass == end_state_first_pass


def test_rollback_resurrects_killed_enemy(build_level) -> None:
    level = build_level()
    level.rollback_enabled = True
    level.rollback = type(level.rollback)(capacity=64)

    enemy = create_enemy(
        name="goblin",
        pos=(300.0, 100.0),
        groups=(level.groups.all_sprites,),
        collision_sprites=level.groups.collision_sprites,
        player_reference=level.player,
    )
    level.groups.combat_sprites.add(enemy)
    level.groups.entity_sprites.add(enemy)
    enemy.spatial_hash = level.spatial_hash

    # Tick 0: enemy alive, captured.
    level.update(1 / 60)
    assert level.rollback.latest_tick == 0
    assert enemy in level.groups.entity_sprites

    # Tick 1: kill the enemy; remove_dead_entities reaps it.
    enemy.health = 0.0
    level.update(1 / 60)
    assert enemy not in level.groups.entity_sprites
    assert enemy.is_dead

    # Roll back to tick 0: enemy must reappear and be alive.
    assert level.rollback.rollback_to(level, 0) is True
    assert enemy in level.groups.entity_sprites
    assert enemy.is_dead is False
    assert enemy.health == pytest.approx(enemy.max_health)


def test_rollback_reaps_entity_spawned_after_snapshot(build_level) -> None:
    level = build_level()
    level.rollback_enabled = True
    level.rollback = type(level.rollback)(capacity=64)

    # Tick 0: no enemy yet.
    level.update(1 / 60)

    # Tick 1: spawn an enemy "at runtime" and tick once more.
    enemy = create_enemy(
        name="goblin",
        pos=(300.0, 100.0),
        groups=(level.groups.all_sprites,),
        collision_sprites=level.groups.collision_sprites,
        player_reference=level.player,
    )
    level.groups.combat_sprites.add(enemy)
    level.groups.entity_sprites.add(enemy)
    enemy.spatial_hash = level.spatial_hash
    level.update(1 / 60)
    assert enemy in level.groups.entity_sprites

    # Roll back to tick 0 — the spawn happened AFTER, so it must be reaped.
    assert level.rollback.rollback_to(level, 0) is True
    assert enemy not in level.groups.entity_sprites
    assert enemy.is_dead is False  # not killed, just removed from groups
