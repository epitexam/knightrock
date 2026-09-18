"""Void-edge detection and the shared ledge state (common to all entities)."""

import os
import random
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest
from pygame.math import Vector2

from src.core.settings import Ledge
from src.entities.enemies.enemy import Enemy
from src.entities.enemies.schema import EnemyConfig
from src.states.enemy_states import EnemyChaseState, EnemyPatrolState, EnemyState
from src.states.ledge_state import LedgeState
from src.ui.world_ui import WorldUI
from tests.unit.helpers import make_entity


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def _tile(top: float = 200.0, left: float = 0.0, width: float = 400.0) -> SimpleNamespace:
    box = pygame.FRect(left, top, width, 64)
    return SimpleNamespace(rect=box, hitbox=box, old_hitbox=box.copy())


def _grounded(entity, colliders) -> None:
    entity.collision_sprites = list(colliders)
    entity.on_surface["floor"] = True


# --- Entity.is_at_ledge ----------------------------------------------------


def test_ground_ahead_is_not_a_ledge() -> None:
    entity = make_entity(pos=(100.0, 152.0))
    _grounded(entity, [_tile()])
    entity.facing_right = True

    assert not entity.is_at_ledge()


def test_void_ahead_is_a_ledge() -> None:
    entity = make_entity(pos=(370.0, 152.0))
    _grounded(entity, [_tile()])
    entity.facing_right = True

    assert entity.is_at_ledge()


def test_probe_follows_facing_direction() -> None:
    entity = make_entity(pos=(370.0, 152.0))
    _grounded(entity, [_tile()])

    entity.facing_right = True
    assert entity.is_at_ledge()
    entity.facing_right = False
    assert not entity.is_at_ledge()


def test_probe_leads_with_the_walk_axis_not_stale_facing() -> None:
    entity = make_entity(pos=(370.0, 152.0))
    _grounded(entity, [_tile()])
    entity.facing_right = False  # stale: the walk axis must win

    entity.move_axis = 1.0
    assert entity.is_at_ledge()
    entity.move_axis = -1.0
    assert not entity.is_at_ledge()


def test_airborne_entities_are_never_at_a_ledge() -> None:
    entity = make_entity(pos=(370.0, 100.0))
    entity.collision_sprites = [_tile()]
    entity.on_surface["floor"] = False
    entity.facing_right = True

    assert not entity.is_at_ledge()


def test_one_way_platforms_count_as_ground() -> None:
    entity = make_entity(pos=(100.0, 152.0))
    tile = _tile()
    tile.one_way = True
    _grounded(entity, [tile])
    entity.facing_right = True

    assert not entity.is_at_ledge()


def test_no_colliders_means_void() -> None:
    entity = make_entity(pos=(100.0, 152.0))
    _grounded(entity, [])
    entity.facing_right = True

    assert entity.is_at_ledge()


def test_turn_around_flips_facing() -> None:
    entity = make_entity()
    entity.facing_right = True

    entity.turn_around()

    assert entity.facing_right is False


# --- LedgeState --------------------------------------------------------------


def _ledge_stub() -> SimpleNamespace:
    return SimpleNamespace(
        move_axis=1.0,
        facing_right=True,
        on_surface={"floor": True},
        velocity=Vector2(120.0, 0.0),
        turn_around=Mock(),
        is_at_ledge=Mock(return_value=False),
    )


def test_ledge_enter_cuts_locomotion_and_turns() -> None:
    entity = _ledge_stub()
    state = LedgeState(entity, exit_resolver=lambda: "idle")

    state.enter()

    assert entity.move_axis == pytest.approx(0.0)
    entity.turn_around.assert_called_once_with()


def test_ledge_exits_once_turned_and_hold_expired() -> None:
    entity = _ledge_stub()
    seen: list[str] = []
    state = LedgeState(entity, exit_resolver=lambda: seen.append("idle") or "idle")
    state.enter()

    assert state.update(0.1) is None
    assert state.update(0.3) == "idle"
    assert seen == ["idle"]
    assert entity.velocity.x < 120.0


def test_ledge_waits_while_still_facing_the_void() -> None:
    entity = _ledge_stub()
    entity.is_at_ledge = Mock(return_value=True)
    state = LedgeState(entity, exit_resolver=lambda: "idle")
    state.enter()

    assert state.update(10.0) is None


# --- Enemy wiring --------------------------------------------------------------


def _patrol_stub(*, at_ledge: bool) -> SimpleNamespace:
    return SimpleNamespace(
        direction=1,
        patrol_interval=2.0,
        patrol_direction=1,
        facing_right=True,
        move_axis=0.0,
        on_surface={"floor": True},
        can_see_player=Mock(return_value=False),
        is_at_ledge=Mock(return_value=at_ledge),
        apply_horizontal_movement=Mock(),
        state_machine=SimpleNamespace(change_state=Mock()),
    )


def test_patrol_steps_into_ledge_state_at_the_edge() -> None:
    entity = _patrol_stub(at_ledge=True)
    state = EnemyPatrolState(entity)
    state.enter()

    state.update(1 / 60)

    entity.state_machine.change_state.assert_called_once_with(EnemyState.LEDGE)
    entity.apply_horizontal_movement.assert_not_called()


def test_patrol_walks_with_a_stale_facing_away_from_edges() -> None:
    entity = _patrol_stub(at_ledge=False)
    entity.patrol_direction = -1
    entity.facing_right = True  # stale: patrol must not rewrite it
    state = EnemyPatrolState(entity)
    state.enter()

    state.update(1 / 60)

    assert entity.move_axis == -1
    assert entity.facing_right is True
    entity.state_machine.change_state.assert_not_called()


def _chase_stub(*, at_ledge: bool) -> SimpleNamespace:
    return SimpleNamespace(
        player=SimpleNamespace(hitbox=pygame.FRect(500, 150, 40, 48)),
        hitbox=pygame.FRect(100, 150, 40, 48),
        move_axis=0.0,
        facing_right=True,
        on_surface={"floor": True},
        combat=SimpleNamespace(),
        is_player_in_range=Mock(return_value=False),
        can_see_player=Mock(return_value=True),
        is_at_ledge=Mock(return_value=at_ledge),
        apply_horizontal_movement=Mock(),
        state_machine=SimpleNamespace(change_state=Mock()),
    )


def test_chase_refuses_to_run_off_the_edge() -> None:
    entity = _chase_stub(at_ledge=True)
    state = EnemyChaseState(entity)

    state.update(1 / 60)

    entity.state_machine.change_state.assert_called_once_with(EnemyState.LEDGE)


def test_chase_keeps_running_with_ground_ahead() -> None:
    entity = _chase_stub(at_ledge=False)
    state = EnemyChaseState(entity)

    state.update(1 / 60)

    assert entity.move_axis == pytest.approx(1.0)
    entity.apply_horizontal_movement.assert_called_once_with(pytest.approx(1 / 60))
    entity.state_machine.change_state.assert_not_called()


def _ai_config() -> EnemyConfig:
    return EnemyConfig(
        size=(40.0, 48.0),
        color=(200, 60, 60),
        health=100.0,
        attacks={},
        chase_speed=120.0,
        vision_range=0.0,
        attack_range=0.0,
        # The timer must never flip mid-test: only the ledge may turn it.
        patrol_interval=30.0,
        animations={},
    )


def test_patrolling_enemy_turns_at_the_cliff_instead_of_falling() -> None:
    tile = _tile()
    enemy = Enemy(
        pos=(300.0, 152.0),
        groups=pygame.sprite.Group(),
        collision_sprites=[tile],
        player_reference=None,
        config=_ai_config(),
        rng=random.Random(1),
    )
    enemy.patrol_direction = 1
    enemy.facing_right = False  # stale: the walk axis still probes ahead

    for _ in range(300):
        enemy.update(1 / 60)

    assert EnemyState.LEDGE in list(enemy.state_machine.history)
    assert enemy.patrol_direction == -1
    assert enemy.facing_right is True
    assert enemy.on_surface["floor"]
    assert enemy.hitbox.bottom == pytest.approx(tile.hitbox.top)
    # Braked right at the edge: front foot may lean past it by less than
    # the probe width, but the body never walks off into the void.
    assert enemy.hitbox.right <= tile.hitbox.right + Ledge.PROBE_AHEAD_PX
    assert enemy.hitbox.centerx < tile.hitbox.right


def test_enemy_turn_around_keeps_the_patrol_leg_in_sync() -> None:
    tile = _tile()
    enemy = Enemy(
        pos=(100.0, 152.0),
        groups=pygame.sprite.Group(),
        collision_sprites=[tile],
        player_reference=None,
        config=_ai_config(),
        rng=random.Random(1),
    )
    enemy.facing_right = True
    enemy.patrol_direction = 1

    enemy.turn_around()

    assert enemy.facing_right is False
    assert enemy.patrol_direction == -1


# --- Debug flag ------------------------------------------------------------------


def test_debug_labels_flag_entities_at_a_ledge() -> None:
    machine = SimpleNamespace(current_state_name="patrol")
    at_ledge = SimpleNamespace(
        health=100.0,
        max_health=100.0,
        combat=SimpleNamespace(state=SimpleNamespace(attack_name=None)),
        stagger_timer=0.0,
        otg_timer=0.0,
        gravity_scale=1.0,
        on_surface={"floor": True},
        is_at_ledge=lambda: True,
    )
    safe = SimpleNamespace(
        health=100.0,
        max_health=100.0,
        combat=SimpleNamespace(state=SimpleNamespace(attack_name=None)),
        stagger_timer=0.0,
        otg_timer=0.0,
        gravity_scale=1.0,
        on_surface={"floor": True},
        is_at_ledge=lambda: False,
    )

    assert any("LEDGE" in line for line in WorldUI._entity_lines(at_ledge, machine))
    assert not any("LEDGE" in line for line in WorldUI._entity_lines(safe, machine))
