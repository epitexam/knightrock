"""Behavioral tests for simulation suspension and player configuration."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.core.gameplay.gameplay_loop import GameplayLoop
from src.core.level.level import Level
from src.core.settings import Combat, Physics
from src.entities.player_config import PlayerConfig
from src.physics.movement import resolve_jump
from src.states.player_states import PlayerBlockState, PlayerDashState


class TrackingGroup(list):
    """Small group double that records update calls while remaining iterable."""

    def __init__(self, *sprites):
        super().__init__(sprites)
        self.update = Mock()


def test_hit_stop_suspends_the_tick_that_expires_it() -> None:
    loop = GameplayLoop()
    loop.combat_system.hit_stop_timer = 0.01

    effective_delta = loop.begin_tick(0.02)

    assert effective_delta == 0.0
    assert loop.combat_system.hit_stop_timer == 0.0
    assert loop.begin_tick(0.02) == pytest.approx(0.02)


def test_level_hit_stop_freezes_simulation_side_effects(monkeypatch) -> None:
    player = SimpleNamespace(
        is_dead=False,
        hitbox=pygame.FRect(0, 0, 48, 56),
        respawn=Mock(),
    )
    dead_enemy = SimpleNamespace(is_dead=True, kill=Mock())
    groups = SimpleNamespace(
        moving_platforms=TrackingGroup(),
        hazard_sprites=TrackingGroup(),
        entity_sprites=TrackingGroup(player, dead_enemy),
        fx_sprites=TrackingGroup(),
        combat_sprites=TrackingGroup(),
        exit_sprites=TrackingGroup(),
    )

    level = Level.__new__(Level)
    level.player = player  # type: ignore[assignment]
    level.groups = groups  # type: ignore[assignment]
    level.exit_reached = False
    level.respawn_timer = 0.75
    level.debug_controller = SimpleNamespace(update=Mock())  # type: ignore[assignment]
    level.camera = SimpleNamespace(follow=Mock())  # type: ignore[assignment]
    level.contact_damage_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.hazard_damage_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.gameplay_loop = GameplayLoop()
    level.gameplay_loop.combat_system.hit_stop_timer = 0.1
    level.gameplay_loop.separation_system.process = Mock()
    level.gameplay_loop.combat_system.process_attacks = Mock()

    exit_check = Mock(return_value=[object()])
    monkeypatch.setattr(pygame.sprite, "spritecollide", exit_check)

    level.update(0.016)

    level.debug_controller.update.assert_called_once_with(  # type: ignore[attr-defined]
        0.016, player)
    level.camera.follow.assert_called_once_with(  # type: ignore[attr-defined]
        player.hitbox, 0.016)
    groups.moving_platforms.update.assert_not_called()
    groups.hazard_sprites.update.assert_not_called()
    groups.entity_sprites.update.assert_not_called()
    groups.fx_sprites.update.assert_not_called()
    level.gameplay_loop.separation_system.process.assert_not_called()
    level.gameplay_loop.combat_system.process_attacks.assert_not_called()
    level.contact_damage_system.process.assert_not_called()  # type: ignore[attr-defined]
    level.hazard_damage_system.process.assert_not_called()  # type: ignore[attr-defined]
    dead_enemy.kill.assert_not_called()
    player.respawn.assert_not_called()
    exit_check.assert_not_called()
    assert level.respawn_timer == pytest.approx(0.75)
    assert level.exit_reached is False


def test_wall_jump_uses_entity_configuration() -> None:
    entity = SimpleNamespace(
        velocity=pygame.Vector2(),
        speed=320.0,
        on_surface={"floor": False, "left": True, "right": False},
        jump_buffer_timer=0.2,
        coyote_timer=0.0,
        jump_height=500.0,
        wall_jump_height=612.0,
        wall_jump_push_multiplier=1.75,
        wall_jump_lock_timer=0.0,
        wall_jump_lock_duration=0.27,
        wall_jump_min_lock=0.09,
        wall_jumps_left=2,
        midair_jumps_left=1,
    )

    resolve_jump(entity)  # type: ignore[arg-type]

    assert entity.velocity.y == pytest.approx(-612.0)
    assert entity.velocity.x == pytest.approx(560.0)
    assert entity.wall_jump_lock_timer == pytest.approx(0.27)
    assert entity.wall_jumps_left == 1
    assert entity.jump_buffer_timer == 0.0


@pytest.mark.parametrize(
    ("stamina", "attribute", "expected"),
    [
        (0.5, "block_cooldown_normal", 0.9),
        (0.0, "block_cooldown_broken", 3.4),
    ],
)
def test_block_exit_uses_exposed_cooldown_configuration(
    stamina: float, attribute: str, expected: float
) -> None:
    entity = SimpleNamespace(
        block_stamina=stamina,
        block_cooldown_timer=0.0,
        block_cooldown_normal=0.9,
        block_cooldown_broken=3.4,
        hitbox=pygame.FRect(0, 0, 48, 40),
        handle_collisions=Mock(),
        sync_rects=Mock(),
    )

    PlayerBlockState(entity).exit()

    assert getattr(entity, attribute) == expected
    assert entity.block_cooldown_timer == pytest.approx(expected)
    entity.handle_collisions.assert_called_once_with("vertical")


def test_dash_uses_exposed_recharge_and_gravity_configuration() -> None:
    entity = SimpleNamespace(
        dash_charges=2,
        dash_recharge_timer=0.0,
        dash_recharge_time=0.85,
        dash_penalty_timer=0.0,
        dash_penalty_duration=2.0,
        dash_speed=1200.0,
        dash_duration=0.5,
        dash_friction=2.0,
        dash_gravity_mult=0.4,
        normal_gravity=2000.0,
        _dash_requested=True,
        _dash_duration_timer=0.0,
        _original_hitbox_width=0.0,
        facing_right=True,
        left_held=False,
        right_held=False,
        velocity=pygame.Vector2(),
        hitbox=pygame.FRect(0, 0, 50, 60),
        on_surface={"floor": False, "left": False, "right": False},
    )
    state = PlayerDashState(entity)

    state.enter()
    next_state = state.update(0.1)

    assert entity.dash_charges == 1
    assert entity.dash_recharge_timer == pytest.approx(0.85)
    assert entity.velocity.y == pytest.approx(80.0)
    assert next_state is None


def test_player_config_defaults_follow_central_settings() -> None:
    config = PlayerConfig()

    assert config.speed == Physics.PLAYER_SPEED
    assert config.dash_recharge_time == Physics.DASH_RECHARGE_TIME
    assert config.dash_gravity_mult == Physics.DASH_GRAVITY_MULT
    assert config.block_cooldown_normal == Combat.BLOCK_COOLDOWN_NORMAL
    assert config.block_cooldown_broken == Combat.BLOCK_COOLDOWN_BROKEN
