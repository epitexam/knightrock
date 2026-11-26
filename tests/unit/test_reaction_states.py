"""Behavioral tests for the shared reaction states (ARCH-05 factorization)."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame

from src.simulation.states.reaction_states import HurtState, KnockbackState, StaggerState


def make_entity(*, is_hurt: bool = False, stagger: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        velocity=pygame.Vector2(300.0, 0.0),
        on_surface={"floor": True, "left": False, "right": False},
        combat=SimpleNamespace(is_hurt=is_hurt),
        stagger_timer=stagger,
        dash_requested=True,
        move_axis=0.0,
    )


def test_hurt_state_exits_when_hurt_timer_clears() -> None:
    entity = make_entity(is_hurt=True)
    state = HurtState(entity, lambda: "idle")

    assert state.update(1 / 60) is None
    entity.combat.is_hurt = False
    assert state.update(1 / 60) == "idle"


def test_hurt_state_slows_the_push() -> None:
    entity = make_entity(is_hurt=True)
    state = HurtState(entity, lambda: None)
    state.update(1 / 60)

    assert entity.velocity.x < 300.0


def test_knockback_state_applies_launch_on_enter() -> None:
    entity = make_entity()
    state = KnockbackState(entity, lambda: None)

    state.enter(
        knockback_direction=-1.0,
        knockback_force=200.0,
        knockback_up_force=150.0,
    )

    assert entity.velocity.x == -200.0
    assert entity.velocity.y == 150.0  # BUG-04: knockback_up_force is applied as-is (no inversion)


def test_knockback_state_exits_when_landed_and_slowed() -> None:
    entity = make_entity()
    exit_resolver = Mock(return_value="idle")
    state = KnockbackState(entity, exit_resolver)

    state.enter(knockback_direction=1.0, knockback_force=200.0, knockback_up_force=0.0)
    entity.on_surface = {"floor": False, "left": False, "right": False}
    assert state.update(1 / 60) is None

    entity.on_surface = {"floor": True, "left": False, "right": False}
    next_state = None
    for _ in range(120):
        next_state = state.update(1 / 60)
        if next_state is not None:
            break

    assert exit_resolver.called
    assert next_state == "idle"


def test_stagger_state_exits_when_timer_clears() -> None:
    entity = make_entity(stagger=0.5)
    state = StaggerState(entity, lambda: "idle")

    assert state.update(1 / 60) is None
    entity.stagger_timer = 0.0
    assert state.update(1 / 60) == "idle"


def test_a_staggered_fighter_slides_to_a_stop_instead_of_gliding() -> None:
    """The push used to hold its full speed for the whole stun, then stop dead."""
    entity = make_entity(stagger=0.5)
    state = StaggerState(entity, lambda: "idle")

    speeds = []
    for _ in range(30):
        state.update(1 / 60)
        speeds.append(entity.velocity.x)

    assert speeds[0] < 300.0
    assert all(later <= earlier for earlier, later in zip(speeds, speeds[1:], strict=False))
    assert speeds[-1] == 0.0


def test_the_slide_stops_in_finite_time_without_a_crawl() -> None:
    """The last pixels are not an asymptote: the speed reaches zero, and soon."""
    entity = make_entity(stagger=5.0)
    state = StaggerState(entity, lambda: "idle")

    frames = 0
    while entity.velocity.x > 0.0 and frames < 600:
        state.update(1 / 60)
        frames += 1

    assert entity.velocity.x == 0.0
    assert frames <= 20  # 300 px/s: 0.27 s


def test_the_slide_does_not_depend_on_the_frame_rate() -> None:
    slow, fast = make_entity(stagger=5.0), make_entity(stagger=5.0)
    slow_state = StaggerState(slow, lambda: "idle")
    fast_state = StaggerState(fast, lambda: "idle")

    for _ in range(6):
        slow_state.update(1 / 60)
    for _ in range(24):
        fast_state.update(1 / 240)

    assert abs(slow.velocity.x - fast.velocity.x) < 1e-6


def test_the_three_reactions_slow_a_push_alike() -> None:
    """Which reaction a hit triggers does not change how far it sends its target."""
    hurt, staggered, launched = (
        make_entity(is_hurt=True),
        make_entity(stagger=0.5),
        make_entity(),
    )
    HurtState(hurt, lambda: None).update(1 / 60)
    StaggerState(staggered, lambda: None).update(1 / 60)
    KnockbackState(launched, lambda: None).update(1 / 60)

    assert hurt.velocity.x == staggered.velocity.x == launched.velocity.x


def test_a_launch_keeps_its_speed_on_the_tick_it_leaves_the_ground() -> None:
    """The floor flag is a tick late; ground friction must not bite a take-off."""
    entity = make_entity()
    state = KnockbackState(entity, lambda: "idle")
    state.enter(knockback_direction=1.0, knockback_force=400.0, knockback_up_force=-550.0)
    assert entity.on_surface["floor"] is True

    state.update(1 / 60)

    assert entity.velocity.x > 395.0


def test_the_air_barely_slows_a_launch() -> None:
    entity = make_entity()
    entity.on_surface = {"floor": False, "left": False, "right": False}
    state = KnockbackState(entity, lambda: "idle")
    state.enter(knockback_direction=1.0, knockback_force=400.0, knockback_up_force=-550.0)

    for _ in range(30):
        state.update(1 / 60)

    assert 250.0 < entity.velocity.x < 400.0


def test_knockback_state_releases_without_floor_after_timeout() -> None:
    """A launch over a pit exits instead of locking forever (infinite KB)."""
    entity = make_entity()
    entity.on_surface = {"floor": False, "left": False, "right": False}
    state = KnockbackState(entity, lambda: "idle", max_duration=0.5)

    state.enter(knockback_direction=1.0, knockback_force=600.0, knockback_up_force=-300.0)
    for _ in range(29):
        assert state.update(1 / 60) is None

    exited = None
    for _ in range(10):
        exited = state.update(1 / 60)
        if exited is not None:
            break

    assert exited == "idle"


def test_knockback_reentry_resets_the_timeout() -> None:
    """Juggling re-arms the safety cap instead of inheriting a stale timer."""
    entity = make_entity()
    entity.on_surface = {"floor": False, "left": False, "right": False}
    state = KnockbackState(entity, lambda: "idle", max_duration=0.5)

    state.enter(knockback_direction=1.0, knockback_force=600.0, knockback_up_force=0.0)
    for _ in range(20):
        state.update(1 / 60)
    state.enter(knockback_direction=1.0, knockback_force=600.0, knockback_up_force=0.0)
    for _ in range(20):
        assert state.update(1 / 60) is None
