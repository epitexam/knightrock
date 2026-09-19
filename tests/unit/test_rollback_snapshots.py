"""Round-trip tests for every snapshot primitive (Phase 3 #3).

Each test captures a component/entity at a specific simulation moment,
mutates it, then restores from the snapshot and asserts the restored
state is bit-exact.  This is the building block the
``test_rollback_e2e`` harness relies on for whole-level determinism.
"""

from __future__ import annotations

import random

import pytest
from pygame.math import Vector2
from pygame.sprite import Group

from src.entities.entity import Entity
from src.entities.player import Player
from src.entities.player_controllers import (
    DashController,
    DashSnapshot,
    GuardController,
    GuardSnapshot,
    JumpController,
    JumpSnapshot,
)
from src.entities.vitals import Vitals
from src.states.null_state_machine import NullStateMachine
from src.states.state_machine import State, StateMachine, StateMachineSnapshot
from tests.unit.helpers import InputStub


def test_vitals_round_trip_captures_health_and_timers() -> None:
    vitals = Vitals(health=60.0, max_health=120.0, invincibility_duration=0.3)
    vitals.invincibility_timer = 0.12
    vitals.stagger_timer = 0.5
    vitals.super_armor = True
    vitals.super_armor_count = 2

    snapshot = vitals.save_state()

    vitals.health = 0.0  # triggers on_death callback
    vitals.stagger_timer = 0.0
    vitals.super_armor = False
    vitals.super_armor_count = 0
    vitals.invincibility_timer = 0.0

    vitals.load_state(snapshot)

    assert vitals.health == pytest.approx(60.0)
    assert vitals.max_health == pytest.approx(120.0)
    assert vitals.is_dead is False  # on_death must NOT have fired during load
    assert vitals.invincibility_timer == pytest.approx(0.12)
    assert vitals.stagger_timer == pytest.approx(0.5)
    assert vitals.super_armor is True
    assert vitals.super_armor_count == 2


class _IdleWithTimer(State):
    """State that owns a transient timer — must survive a rollback."""

    def enter(self, previous=None, **kwargs) -> None:
        self.timer = 0.5

    def update(self, delta_time: float):
        self.timer = max(0.0, self.timer - delta_time)
        if self.timer <= 0:
            return "done"
        return None


class _Done(State):
    pass


def test_state_machine_snapshot_restores_transient_attrs_without_enter() -> None:
    entity = type("E", (), {})()
    machine = StateMachine(entity)
    machine.add_state("idle", _IdleWithTimer(entity))
    machine.add_state("done", _Done(entity))
    machine.set_initial_state("idle")

    # Advance the state mid-timer.
    machine.update(0.2)
    assert machine.current_state.timer == pytest.approx(0.3)

    snapshot = machine.save_state()

    # Mutate the live machine past the transition.
    machine.update(0.5)
    assert machine.current_state_name == "done"

    # Restore — this must NOT call enter() (which would reset timer to 0.5).
    machine.load_state(snapshot)

    assert machine.current_state_name == "idle"
    assert machine.current_state.timer == pytest.approx(0.3)


def test_null_state_machine_snapshot_is_neutral() -> None:
    machine = NullStateMachine()
    snapshot = machine.save_state()
    assert isinstance(snapshot, StateMachineSnapshot)
    assert snapshot.current_state_name is None
    machine.load_state(snapshot)  # no-op


def test_jump_controller_snapshot_round_trip() -> None:
    from tests.unit.helpers import make_phase  # noqa: F401  (PlayerConfig source)

    config = _fake_player_config()
    ctrl = JumpController(config)
    ctrl.jump_buffer_timer = 0.11
    ctrl.coyote_timer = 0.07
    ctrl.wall_jump_lock_timer = 0.2
    ctrl.midair_jumps_left = 0
    ctrl.wall_jumps_left = 3

    snapshot = ctrl.save_state()
    assert isinstance(snapshot, JumpSnapshot)

    ctrl.reset()
    assert ctrl.jump_buffer_timer == 0.0

    ctrl.load_state(snapshot)
    assert ctrl.jump_buffer_timer == pytest.approx(0.11)
    assert ctrl.coyote_timer == pytest.approx(0.07)
    assert ctrl.wall_jump_lock_timer == pytest.approx(0.2)
    assert ctrl.midair_jumps_left == 0
    assert ctrl.wall_jumps_left == 3


def test_guard_and_dash_controller_snapshots() -> None:
    config = _fake_player_config()
    guard = GuardController(config)
    guard.posture = 42.0
    guard.lockout_timer = 0.33
    guard.parry_timer = 0.1
    guard.riposte_timer = 0.2
    snap_guard = guard.save_state()
    assert isinstance(snap_guard, GuardSnapshot)
    guard.reset()
    guard.load_state(snap_guard)
    assert guard.posture == pytest.approx(42.0)
    assert guard.lockout_timer == pytest.approx(0.33)
    assert guard.parry_timer == pytest.approx(0.1)
    assert guard.riposte_timer == pytest.approx(0.2)

    dash = DashController(config, original_hitbox_width=48.0)
    dash.charges = 0
    dash.recharge_timer = 1.5
    dash.penalty_timer = 0.8
    dash.requested = True
    dash.duration_timer = 0.1
    dash.original_hitbox_width = 30.0
    snap_dash = dash.save_state()
    assert isinstance(snap_dash, DashSnapshot)
    dash.reset()
    dash.load_state(snap_dash)
    assert dash.charges == 0
    assert dash.recharge_timer == pytest.approx(1.5)
    assert dash.penalty_timer == pytest.approx(0.8)
    assert dash.requested is True
    assert dash.duration_timer == pytest.approx(0.1)
    assert dash.original_hitbox_width == pytest.approx(30.0)


def test_entity_snapshot_round_trip_preserves_rng_state() -> None:
    rng = random.Random(42)
    entity = Entity(
        pos=(50.0, 80.0),
        size=(40.0, 50.0),
        color=(128, 128, 128),
        groups=Group(),
        collision_sprites=Group(),
        health=80.0,
        rng=rng,
    )
    entity.velocity = Vector2(100.0, -50.0)
    entity.on_surface["floor"] = True
    entity.facing_right = False
    entity.move_axis = -1.0

    snapshot = entity.save_state()

    # Advance rng and flip everything.
    rng.random()
    entity.velocity = Vector2(0.0, 0.0)
    entity.on_surface["floor"] = False
    entity.facing_right = True
    entity.move_axis = 0.0

    entity.load_state(snapshot)

    assert (entity.velocity.x, entity.velocity.y) == pytest.approx((100.0, -50.0))
    assert entity.on_surface == {"floor": True, "left": False, "right": False}
    assert entity.facing_right is False
    assert entity.move_axis == -1.0
    # RNG state must have been rewound so next calls match the snapshot's rng.
    expected_rng = random.Random(42)
    assert rng.random() == pytest.approx(expected_rng.random())


def test_entity_snapshot_captures_combat_and_state_machine() -> None:
    from tests.unit.helpers import make_attack, make_phase

    phase = make_phase(startup=1, active=1, recovery=1)
    entity = Entity(
        pos=(100.0, 100.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
        attacks={"test": make_attack(phase)},
    )
    assert entity.combat.start_attack("test")
    entity.combat.update(1 / 60)  # advance one attack frame

    snapshot = entity.save_state()

    assert snapshot.combat.attack_state.attack_name == "test"
    assert snapshot.state_machine.current_state_name is None  # NullStateMachine

    # End the attack then restore — must bring the machine back mid-attack.
    entity.combat.state.end()
    assert entity.combat.state.attack_name is None
    entity.load_state(snapshot)
    assert entity.combat.state.attack_name == "test"


def test_player_snapshot_restores_controllers_and_buffered_attack() -> None:
    groups = Group()
    player = Player(
        pos=(100.0, 100.0),
        groups=groups,
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )

    player.jump.jump_buffer_timer = 0.14
    player.jump.midair_jumps_left = 0
    player.guard.posture = 25.0
    player.dash.charges = 0
    player.dash.penalty_timer = 0.5
    player.input_handler.buffered_attack_name = "light_attack"
    player.left_held = True
    player.right_held = False
    player.guard_held = True

    snapshot = player.save_state()

    player.jump.reset()
    player.guard.reset()
    player.dash.reset()
    player.input_handler.buffered_attack_name = None
    player.left_held = False
    player.guard_held = False

    player.load_state(snapshot)

    assert player.jump.jump_buffer_timer == pytest.approx(0.14)
    assert player.jump.midair_jumps_left == 0
    assert player.guard.posture == pytest.approx(25.0)
    assert player.dash.charges == 0
    assert player.dash.penalty_timer == pytest.approx(0.5)
    assert player.input_handler.buffered_attack_name == "light_attack"
    assert player.left_held is True
    assert player.right_held is False
    assert player.guard_held is True


def _fake_player_config():
    from src.entities.player_config import DEFAULT_PLAYER_CONFIG

    return DEFAULT_PLAYER_CONFIG
