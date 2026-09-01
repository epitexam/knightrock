"""Behavioral tests for the shared reaction states (ARCH-05 factorization)."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame

from src.states.reaction_states import HurtState, KnockbackState, StaggerState


def make_entity(*, is_hurt: bool = False, stagger: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        velocity=pygame.Vector2(300.0, 0.0),
        on_surface={"floor": True, "left": False, "right": False},
        combat=SimpleNamespace(is_hurt=is_hurt),
        stagger_timer=stagger,
        dash_requested=True,
    )


def test_hurt_state_exits_when_hurt_timer_clears() -> None:
    entity = make_entity(is_hurt=True)
    state = HurtState(entity, lambda: "idle", friction=8.0)

    assert state.update(1 / 60) is None
    entity.combat.is_hurt = False
    assert state.update(1 / 60) == "idle"


def test_hurt_state_applies_configured_friction() -> None:
    entity = make_entity(is_hurt=True)
    state = HurtState(entity, lambda: None, friction=8.0)
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
    state = StaggerState(entity, lambda: "idle", friction=8.0)

    assert state.update(1 / 60) is None
    entity.stagger_timer = 0.0
    assert state.update(1 / 60) == "idle"


def test_stagger_state_does_not_apply_friction_when_friction_zero() -> None:
    entity = make_entity(stagger=0.5)
    state = StaggerState(entity, lambda: "idle", friction=0.0)

    state.update(1 / 60)

    assert entity.velocity.x == 300.0