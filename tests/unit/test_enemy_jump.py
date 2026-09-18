"""Per-type enemy jump: only jump-capable types hop, only while chasing."""

import os
import random
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest
from pygame.math import Vector2

from src.entities.enemies.configs import ENEMY_CONFIGS
from src.entities.enemies.enemy import Enemy
from src.entities.enemies.schema import EnemyConfig
from src.states.enemy_states import EnemyChaseState, EnemyState
from tests.unit.helpers import make_entity


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def _tile(left: float, top: float, width: float = 400.0, height: float = 64.0):
    box = pygame.FRect(left, top, width, height)
    return SimpleNamespace(rect=box, hitbox=box, old_hitbox=box.copy())


def _jumper_stub(*, wall: bool = False, above: bool = False) -> SimpleNamespace:
    player_y = 50.0 if above else 160.0
    return SimpleNamespace(
        can_jump=True,
        jump_height=500.0,
        jump_cooldown=1.0,
        hitbox=pygame.FRect(100, 152, 40, 48),
        move_axis=1.0,
        facing_right=True,
        on_surface={"floor": True, "left": False, "right": wall},
        velocity=Vector2(0, 0),
        combat=SimpleNamespace(),
        player=SimpleNamespace(hitbox=pygame.FRect(300, player_y, 40, 48)),
        is_player_in_range=Mock(return_value=False),
        can_see_player=Mock(return_value=True),
        is_at_ledge=Mock(return_value=False),
        apply_horizontal_movement=Mock(),
        state_machine=SimpleNamespace(change_state=Mock()),
    )


def test_only_configured_types_can_jump() -> None:
    assert ENEMY_CONFIGS["goblin"].can_jump is True
    assert ENEMY_CONFIGS["slime"].can_jump is False
    assert ENEMY_CONFIGS["dummy"].can_jump is False


def test_chaser_hops_at_a_wall() -> None:
    entity = _jumper_stub(wall=True)
    state = EnemyChaseState(entity)

    state.update(1 / 60)

    assert entity.velocity.y == pytest.approx(-500.0)
    assert state.jump_cooldown_timer == pytest.approx(1.0)


def test_chaser_hops_up_toward_the_player() -> None:
    entity = _jumper_stub(above=True)
    state = EnemyChaseState(entity)

    state.update(1 / 60)

    assert entity.velocity.y == pytest.approx(-500.0)


def test_chaser_stays_grounded_without_trigger() -> None:
    entity = _jumper_stub()
    state = EnemyChaseState(entity)

    state.update(1 / 60)

    assert entity.velocity.y == pytest.approx(0.0)


def test_jump_cooldown_blocks_immediate_rehops() -> None:
    entity = _jumper_stub(wall=True)
    state = EnemyChaseState(entity)

    state.update(1 / 60)
    entity.velocity.y = 0.0
    state.update(1 / 60)

    assert entity.velocity.y == pytest.approx(0.0)

    state.update(1.0)
    assert entity.velocity.y == pytest.approx(-500.0)


def test_jumpers_never_leave_the_ground_mid_air() -> None:
    entity = _jumper_stub(wall=True)
    entity.on_surface["floor"] = False
    state = EnemyChaseState(entity)

    state.update(1 / 60)

    assert entity.velocity.y == pytest.approx(0.0)


def test_non_jumpers_ignore_walls_and_high_players() -> None:
    for stub in (_jumper_stub(wall=True), _jumper_stub(above=True)):
        stub.can_jump = False
        state = EnemyChaseState(stub)

        state.update(1 / 60)

        assert stub.velocity.y == pytest.approx(0.0)


def _jump_config() -> EnemyConfig:
    return EnemyConfig(
        size=(40.0, 48.0),
        color=(60, 130, 60),
        health=60.0,
        attacks={},
        chase_speed=120.0,
        vision_range=400.0,
        attack_range=0.0,
        can_jump=True,
        jump_height=600.0,
        jump_cooldown=1.0,
        animations={},
    )


def _chasing_enemy(can_jump: bool) -> Enemy:
    config = _jump_config()
    cfg = EnemyConfig(
        size=config.size,
        color=config.color,
        health=config.health,
        attacks={},
        chase_speed=config.chase_speed,
        vision_range=config.vision_range,
        attack_range=config.attack_range,
        can_jump=can_jump,
        jump_height=config.jump_height,
        jump_cooldown=config.jump_cooldown,
        animations={},
    )
    floor = _tile(0.0, 200.0)
    wall = _tile(200.0, 100.0, width=32.0, height=200.0)
    player = SimpleNamespace(hitbox=pygame.FRect(500, 150, 40, 48))
    enemy = Enemy(
        pos=(100.0, 152.0),
        groups=pygame.sprite.Group(),
        collision_sprites=[floor, wall],
        player_reference=player,
        config=cfg,
        rng=random.Random(3),
    )
    enemy.state_machine.change_state(EnemyState.CHASE)
    return enemy


def test_goblin_like_enemy_jumps_its_wall_while_chasing() -> None:
    enemy = _chasing_enemy(can_jump=True)
    start_y = enemy.hitbox.y

    for _ in range(120):
        enemy.update(1 / 60)
        if enemy.hitbox.y < start_y - 5.0:
            break

    assert enemy.hitbox.y < start_y - 5.0


def test_ground_bound_enemy_stays_stuck_at_its_wall() -> None:
    enemy = _chasing_enemy(can_jump=False)
    start_y = enemy.hitbox.y

    for _ in range(120):
        enemy.update(1 / 60)

    assert enemy.hitbox.y >= start_y - 1.0
    assert enemy.hitbox.bottom == pytest.approx(200.0)


def test_jump_cooldown_round_trips_through_rollback() -> None:
    enemy = _chasing_enemy(can_jump=True)
    chase = enemy.state_machine.states[EnemyState.CHASE]
    chase.jump_cooldown_timer = 0.5

    snapshot = enemy.state_machine.save_state()
    chase.jump_cooldown_timer = 0.0
    enemy.state_machine.load_state(snapshot)

    assert chase.jump_cooldown_timer == pytest.approx(0.5)


def _gap_chase_enemy(
    *,
    can_jump: bool,
    player_pos: tuple[float, float] = (350.0, 152.0),
    jump_height: float = 700.0,
    leap_mult: float = 1.0,
    gap: float = 40.0,
) -> tuple[Enemy, SimpleNamespace, SimpleNamespace]:
    """A chaser on platform A facing a ``gap`` px void, player across on B."""
    floor_a, floor_b = _gap_world(gap=gap)
    player = SimpleNamespace(hitbox=pygame.FRect(player_pos[0], player_pos[1], 40, 48))
    cfg = EnemyConfig(
        size=(40.0, 48.0),
        color=(60, 130, 60),
        health=60.0,
        attacks={},
        chase_speed=120.0,
        vision_range=400.0,
        attack_range=0.0,
        patrol_interval=30.0,
        can_jump=can_jump,
        jump_height=jump_height,
        jump_cooldown=1.0,
        leap_speed_mult=leap_mult,
        animations={},
    )
    enemy = Enemy(
        pos=(100.0, 152.0),
        groups=pygame.sprite.Group(),
        collision_sprites=[floor_a, floor_b],
        player_reference=player,
        config=cfg,
        rng=random.Random(5),
    )
    enemy.state_machine.change_state(EnemyState.CHASE)
    return enemy, floor_a, floor_b


def test_jumper_leaps_the_gap_to_reach_the_player() -> None:
    enemy, _, floor_b = _gap_chase_enemy(can_jump=True)

    for _ in range(300):
        enemy.update(1 / 60)

    assert enemy.hitbox.x > floor_b.hitbox.left
    assert enemy.on_surface["floor"]
    assert enemy.hitbox.bottom == pytest.approx(floor_b.hitbox.top)


def test_jumper_clears_a_big_gap_with_its_sprint_boost() -> None:
    enemy, _, floor_b = _gap_chase_enemy(can_jump=True, gap=100.0, leap_mult=1.6)

    for _ in range(300):
        enemy.update(1 / 60)

    assert enemy.hitbox.x > floor_b.hitbox.left
    assert enemy.on_surface["floor"]
    assert enemy.hitbox.bottom == pytest.approx(floor_b.hitbox.top)


def test_jumper_attempts_a_small_gap_for_a_far_player() -> None:
    enemy, _, floor_b = _gap_chase_enemy(can_jump=True, player_pos=(450.0, 152.0))

    for _ in range(300):
        enemy.update(1 / 60)

    assert enemy.hitbox.x > floor_b.hitbox.left
    assert enemy.on_surface["floor"]


def test_ground_bound_chaser_turns_instead_of_leaping() -> None:
    enemy, floor_a, _ = _gap_chase_enemy(can_jump=False)

    for _ in range(300):
        enemy.update(1 / 60)

    assert EnemyState.LEDGE in list(enemy.state_machine.history)
    assert enemy.hitbox.right < floor_a.hitbox.right + 30.0
    assert enemy.on_surface["floor"]


def test_jumper_drops_onto_the_floor_below_the_player() -> None:
    enemy, _, floor_b = _gap_chase_enemy(can_jump=True, player_pos=(350.0, 400.0))

    for _ in range(300):
        enemy.update(1 / 60)

    # B catches the fall: the chase walks off A instead of turning.
    assert enemy.hitbox.x > floor_b.hitbox.left
    assert enemy.on_surface["floor"]
    assert enemy.hitbox.bottom == pytest.approx(floor_b.hitbox.top)


def _pit_chase_enemy() -> tuple[Enemy, SimpleNamespace]:
    """A chaser above a bottomless pit, player falling through the void."""
    floor_a = _tile(0.0, 200.0, width=200.0)
    player = SimpleNamespace(hitbox=pygame.FRect(300.0, 420.0, 40, 48))
    cfg = EnemyConfig(
        size=(40.0, 48.0),
        color=(60, 130, 60),
        health=60.0,
        attacks={},
        chase_speed=120.0,
        vision_range=400.0,
        attack_range=0.0,
        patrol_interval=30.0,
        can_jump=True,
        jump_height=700.0,
        jump_cooldown=1.0,
        animations={},
    )
    enemy = Enemy(
        pos=(100.0, 152.0),
        groups=pygame.sprite.Group(),
        collision_sprites=[floor_a],
        player_reference=player,
        config=cfg,
        rng=random.Random(7),
    )
    enemy.state_machine.change_state(EnemyState.CHASE)
    return enemy, floor_a


def test_jumper_refuses_to_dive_into_a_bottomless_pit() -> None:
    enemy, floor_a = _pit_chase_enemy()

    for _ in range(200):
        enemy.update(1 / 60)

    assert EnemyState.LEDGE in list(enemy.state_machine.history)
    assert enemy.hitbox.right < floor_a.hitbox.right + 30.0
    assert enemy.hitbox.bottom == pytest.approx(floor_a.hitbox.top)


def test_jumper_risks_a_slightly_too_wide_gap() -> None:
    floor_a = _tile(0.0, 200.0, width=200.0)
    floor_b = _tile(265.0, 200.0, width=200.0)
    player = SimpleNamespace(hitbox=pygame.FRect(350.0, 152.0, 40, 48))
    cfg = EnemyConfig(
        size=(40.0, 48.0),
        color=(60, 130, 60),
        health=60.0,
        attacks={},
        chase_speed=120.0,
        vision_range=400.0,
        attack_range=0.0,
        patrol_interval=30.0,
        can_jump=True,
        jump_height=700.0,
        jump_cooldown=1.0,
        animations={},
    )
    enemy = Enemy(
        pos=(100.0, 152.0),
        groups=pygame.sprite.Group(),
        collision_sprites=[floor_a, floor_b],
        player_reference=player,
        config=cfg,
        rng=random.Random(9),
    )
    enemy.state_machine.change_state(EnemyState.CHASE)

    for _ in range(300):
        enemy.update(1 / 60)

    assert enemy.hitbox.x > floor_b.hitbox.left
    assert enemy.on_surface["floor"]
    assert enemy.hitbox.bottom == pytest.approx(floor_b.hitbox.top)


def test_jumper_risks_a_deep_drop_onto_the_far_side() -> None:
    floor_a = _tile(0.0, 200.0, width=200.0)
    floor_b = _tile(240.0, 380.0, width=200.0)
    player = SimpleNamespace(hitbox=pygame.FRect(350.0, 332.0, 40, 48))
    cfg = EnemyConfig(
        size=(40.0, 48.0),
        color=(60, 130, 60),
        health=60.0,
        attacks={},
        chase_speed=120.0,
        vision_range=400.0,
        attack_range=0.0,
        patrol_interval=30.0,
        can_jump=True,
        jump_height=700.0,
        jump_cooldown=1.0,
        animations={},
    )
    enemy = Enemy(
        pos=(100.0, 152.0),
        groups=pygame.sprite.Group(),
        collision_sprites=[floor_a, floor_b],
        player_reference=player,
        config=cfg,
        rng=random.Random(11),
    )
    enemy.state_machine.change_state(EnemyState.CHASE)

    for _ in range(300):
        enemy.update(1 / 60)

    assert enemy.hitbox.x > floor_b.hitbox.left
    assert enemy.on_surface["floor"]
    assert enemy.hitbox.bottom == pytest.approx(floor_b.hitbox.top)


def test_jump_range_follows_the_ballistics() -> None:
    # Closed form with Physics.GRAVITY = 1500 (fix "correct gravity value"):
    # apex = 600^2 / (2*1500) = 120, air = 600/1500 + sqrt(2*120/2800).
    enemy = _chasing_enemy(can_jump=True)

    assert enemy.jump_range() == pytest.approx(83.1, abs=0.5)
    assert enemy.jump_apex() == pytest.approx(120.0, abs=0.5)


def test_jump_range_counts_the_sprint_boost() -> None:
    enemy = _chasing_enemy(can_jump=True)
    enemy.leap_speed_mult = 1.6

    assert enemy.jump_range() == pytest.approx(133.0, abs=0.5)
    assert enemy.leap_air_time() == pytest.approx(0.69, abs=0.02)


def _gap_world(gap: float = 40.0):
    """Two same-level platforms: A (0..200) then B after ``gap`` px of void."""
    return _tile(0.0, 200.0, width=200.0), _tile(200.0 + gap, 200.0, width=200.0)


def _edge_entity(floor_a, floor_b) -> object:
    entity = make_entity(pos=(150.0, 160.0))
    entity.collision_sprites = [floor_a, floor_b]
    entity.on_surface["floor"] = True
    entity.move_axis = 1.0
    entity.facing_right = True
    return entity


def test_find_landing_ahead_measures_the_gap() -> None:
    floor_a, floor_b = _gap_world(gap=40.0)
    entity = _edge_entity(floor_a, floor_b)

    landing = entity.find_landing_ahead(200.0, 60.0, 160.0)

    assert landing is not None
    distance, drop = landing
    assert 40.0 < distance <= 60.0
    assert drop == pytest.approx(0.0)


def test_find_landing_ahead_rejects_wide_high_and_missing_ground() -> None:
    floor_a, floor_b = _gap_world(gap=400.0)
    entity = _edge_entity(floor_a, floor_b)

    assert entity.find_landing_ahead(200.0, 60.0, 160.0) is None
    assert entity.find_landing_ahead(0.0, 60.0, 160.0) is None

    high = _tile(240.0, 100.0, width=200.0)
    entity.collision_sprites = [_tile(0.0, 200.0, width=200.0), high]
    assert entity.find_landing_ahead(200.0, 60.0, 160.0) is None

    low = _tile(240.0, 300.0, width=200.0)
    entity.collision_sprites = [_tile(0.0, 200.0, width=200.0), low]
    assert entity.find_landing_ahead(200.0, 60.0, 160.0) is not None
