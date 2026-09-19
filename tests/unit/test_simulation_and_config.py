"""Behavioral tests for simulation suspension and player configuration."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.core.level.level import Level
from src.core.level.level_data import LevelConfig, LevelData
from src.core.level.systems.gameplay_loop import GameplayLoop
from src.core.level.systems.hazard_system import HazardSystem
from src.core.level.systems.physics_system import PhysicsSystem
from src.core.level.systems.platform_system import PlatformSystem
from src.core.level.systems.progression_system import ProgressionSystem
from src.core.level.systems.respawn_system import PlayerRespawnSystem
from src.core.settings import Guard, Physics
from src.entities.player_config import PlayerConfig
from src.entities.player_controllers import DashController, GuardController
from src.physics.movement import resolve_jump
from src.states.player_states import PlayerDashState, PlayerGuardState


class TrackingGroup(list):
    """Small group double that records update calls while remaining iterable."""

    def __init__(self, *sprites):
        super().__init__(sprites)
        self.update = Mock()


def test_hit_stop_suspends_the_tick_that_expires_it() -> None:
    loop = GameplayLoop.combat_only()
    loop.combat_system.hit_stop_timer = 0.01

    effective_delta = loop.begin_tick(0.02)

    assert effective_delta == 0.0
    assert loop.combat_system.hit_stop_timer == 0.0
    assert loop.begin_tick(0.02) == pytest.approx(0.02)


def wire_world_systems(level: Level, groups, player) -> None:
    """Attach the world stages to a ``__new__``-built level (no ``__init__``).

    ``Level`` owns the systems and re-exposes their state, while the gameplay
    loop owns the order in which they run (audit F1.2/F1.6) — both references
    are wired here, with spies where the test asserts "never called".
    """
    level.spatial_hash = SimpleNamespace(update_all=Mock())  # type: ignore[assignment]
    level_data = LevelData(
        width=20,
        height=10,
        tile_size=64,
        object_layers={},
        config=LevelConfig(death_border_bottom=0.0),
    )
    level.respawn_system = PlayerRespawnSystem(player, level_data)  # type: ignore[assignment]
    level.progression_system = ProgressionSystem(groups.exit_sprites)  # type: ignore[assignment]
    level.contact_damage_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.hazard_damage_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.spawn_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.camera_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.notification_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.tick_system = SimpleNamespace(process=Mock())  # type: ignore[assignment]
    level.rollback = Mock()  # type: ignore[assignment]
    level.gameplay_loop = GameplayLoop(  # type: ignore[assignment]
        platform_system=PlatformSystem(groups, level.spatial_hash),
        physics_system=PhysicsSystem(groups),
        hazard_system=HazardSystem(groups),
        contact_damage_system=level.contact_damage_system,
        hazard_damage_system=level.hazard_damage_system,
        respawn_system=level.respawn_system,
        progression_system=level.progression_system,
        spawn_system=level.spawn_system,
        camera_system=level.camera_system,
        notification_system=level.notification_system,
        tick_system=level.tick_system,
    )
    level.gameplay_loop.combat_system.hit_stop_timer = 0.1
    level.gameplay_loop.separation_system.process = Mock()
    level.gameplay_loop.combat_system.process_attacks = Mock()


def test_level_hit_stop_freezes_simulation_side_effects(monkeypatch) -> None:
    """A suspended tick runs no stage of the pipeline (audit F1.6).

    The level is built through ``__new__`` on purpose: the test injects world
    doubles and spies on every stage instead of loading a TMX level.
    """
    player = SimpleNamespace(
        is_dead=False,
        hitbox=pygame.FRect(0, 0, 48, 56),
        respawn=Mock(),
        die=Mock(),
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
    level.tick = 0
    level.rollback_enabled = False
    level.events = None  # type: ignore[assignment]
    wire_world_systems(level, groups, player)

    level.respawn_timer = 0.75
    level.deaths = 0
    level.exit_reached = False

    exit_check = Mock(return_value=[object()])
    monkeypatch.setattr(pygame.sprite, "spritecollide", exit_check)

    level.update(0.016)

    level.spawn_system.process.assert_called_once_with(  # type: ignore[attr-defined]
        0.016, player
    )
    level.camera_system.process.assert_called_once_with(  # type: ignore[attr-defined]
        0.016, player
    )
    level.notification_system.process.assert_called_once()  # type: ignore[attr-defined]
    level.tick_system.process.assert_called_once_with(level, level.rollback)  # type: ignore[attr-defined]
    groups.moving_platforms.update.assert_not_called()
    groups.hazard_sprites.update.assert_not_called()
    groups.entity_sprites.update.assert_not_called()
    groups.fx_sprites.update.assert_not_called()
    level.spatial_hash.update_all.assert_not_called()  # type: ignore[attr-defined]
    level.gameplay_loop.separation_system.process.assert_not_called()
    level.gameplay_loop.combat_system.process_attacks.assert_not_called()
    level.contact_damage_system.process.assert_not_called()  # type: ignore[attr-defined]
    level.hazard_damage_system.process.assert_not_called()  # type: ignore[attr-defined]
    dead_enemy.kill.assert_not_called()
    player.respawn.assert_not_called()
    player.die.assert_not_called()
    exit_check.assert_not_called()
    assert level.respawn_timer == pytest.approx(0.75)
    assert level.exit_reached is False


def test_level_runs_every_pipeline_stage_when_the_tick_is_live(monkeypatch) -> None:
    """Once hit-stop expires the facade runs the whole pipeline (audit F1.6).

    Mirror of the frozen-tick test: same spies, no hit-stop, so every stage
    of ``GameplayLoop.update`` must have run exactly once.
    """
    player = SimpleNamespace(
        is_dead=False,
        hitbox=pygame.FRect(0, 0, 48, 56),
        on_surface={"floor": False, "left": False, "right": False},
        respawn=Mock(),
        die=Mock(),
    )
    dead_enemy = SimpleNamespace(
        is_dead=True,
        hitbox=pygame.FRect(200, 0, 48, 56),
        on_surface={"floor": False, "left": False, "right": False},
        kill=Mock(),
    )
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
    level.tick = 0
    level.rollback_enabled = False
    level.events = None  # type: ignore[assignment]
    wire_world_systems(level, groups, player)
    # No hit-stop: the tick is live.
    level.gameplay_loop.combat_system.hit_stop_timer = 0.0
    level.respawn_timer = 0.0
    level.deaths = 0
    level.exit_reached = False

    exit_check = Mock(return_value=[object()])
    monkeypatch.setattr(pygame.sprite, "spritecollide", exit_check)

    level.update(0.016)

    groups.moving_platforms.update.assert_called_once_with(pytest.approx(0.016))
    groups.hazard_sprites.update.assert_called_once_with(pytest.approx(0.016))
    groups.entity_sprites.update.assert_called_once_with(pytest.approx(0.016))
    groups.fx_sprites.update.assert_called_once_with(pytest.approx(0.016))
    level.spatial_hash.update_all.assert_called_once()  # type: ignore[attr-defined]
    level.gameplay_loop.separation_system.process.assert_called_once()
    level.gameplay_loop.combat_system.process_attacks.assert_called_once()
    level.contact_damage_system.process.assert_called_once()  # type: ignore[attr-defined]
    level.hazard_damage_system.process.assert_called_once()  # type: ignore[attr-defined]
    # The corpse was reaped, the living player was spared and the exit probe ran.
    dead_enemy.kill.assert_called_once()
    player.die.assert_not_called()
    player.respawn.assert_not_called()
    exit_check.assert_called_once()
    assert level.exit_reached is True
    level.spawn_system.process.assert_called_once_with(  # type: ignore[attr-defined]
        0.016, player
    )
    level.camera_system.process.assert_called_once_with(  # type: ignore[attr-defined]
        0.016, player
    )
    level.notification_system.process.assert_called_once()  # type: ignore[attr-defined]
    level.tick_system.process.assert_called_once_with(level, level.rollback)  # type: ignore[attr-defined]


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
    ("posture", "expected"),
    [
        (50.0, "guard"),
        (5.0, "break"),
    ],
)
def test_guard_take_hit_uses_exposed_posture_configuration(posture: float, expected: str) -> None:
    guard = GuardController(PlayerConfig(guard_posture_max=100.0, guard_break_lockout=1.2))
    guard.posture = posture

    outcome, _, _ = guard.take_hit(10.0, False)

    assert outcome == expected


def test_guard_state_moves_slowly_and_releases() -> None:
    entity = SimpleNamespace(
        move_axis=1.0,
        guard=GuardController(PlayerConfig(guard_posture_max=100.0, guard_break_lockout=1.2)),
        guard_held=True,
        velocity=pygame.Vector2(),
        speed=350.0,
        floor_control=25.0,
        air_control=12.0,
        on_surface={"floor": True, "left": False, "right": False},
        combat=SimpleNamespace(movement_multiplier=1.0),
        handle_jump=lambda: None,
        apply_horizontal_movement=lambda dt: setattr(entity, "saw_axis", entity.move_axis),
        left_held=False,
        right_held=True,
        state_machine=SimpleNamespace(current_state_name="guard"),
    )
    state = PlayerGuardState(entity)

    assert state.update(1 / 60) is None
    assert entity.saw_axis == pytest.approx(Guard.MOVE_MULT)
    assert entity.move_axis == pytest.approx(1.0)

    entity.guard_held = False
    assert state.update(1 / 60) == "run"


def test_dash_uses_exposed_recharge_and_gravity_configuration() -> None:
    entity = SimpleNamespace(
        dash=DashController(
            PlayerConfig(
                dash_speed=1200.0,
                dash_duration=0.5,
                dash_friction=2.0,
                dash_recharge_time=0.85,
                dash_gravity_mult=0.4,
            ),
            original_hitbox_width=50.0,
        ),
        facing_right=True,
        left_held=False,
        right_held=False,
        velocity=pygame.Vector2(),
        hitbox=pygame.FRect(0, 0, 50, 60),
        normal_gravity=2000.0,
        on_surface={"floor": False, "left": False, "right": False},
    )
    entity.dash.charges = 2
    state = PlayerDashState(entity)

    state.enter()
    next_state = state.update(0.1)

    assert entity.dash.charges == 1
    assert entity.dash.recharge_timer == pytest.approx(0.85)
    assert entity.dash.duration_timer == pytest.approx(0.4)
    assert entity.hitbox.width == pytest.approx(30.0)
    assert entity.velocity.y == pytest.approx(80.0)
    assert next_state is None


def test_player_config_defaults_follow_central_settings() -> None:
    config = PlayerConfig()

    assert config.speed == Physics.PLAYER_SPEED
    assert config.dash_recharge_time == Physics.DASH_RECHARGE_TIME
    assert config.dash_gravity_mult == Physics.DASH_GRAVITY_MULT
    assert config.guard_posture_max == Guard.MAX_POSTURE
    assert config.guard_break_lockout == Guard.BREAK_LOCKOUT
