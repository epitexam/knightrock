"""BUG-01: knockback/hurt/stagger friction must decay quickly (no double-dt)."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame

from src.states.enemy_states import EnemyKnockbackState
from src.states.player_states import (
    PlayerHurtState,
    PlayerKnockbackState,
    PlayerStaggerState,
)
from src.states.reaction_states import KnockbackState


def make_grounded_player() -> SimpleNamespace:
    return SimpleNamespace(
        velocity=pygame.Vector2(400.0, 0.0),
        on_surface={"floor": True, "left": False, "right": False},
        stagger_timer=0.0,
        combat=SimpleNamespace(is_hurt=False),
        left_held=False,
        right_held=False,
    )


def test_player_knockback_recovery_under_one_second() -> None:
    entity = make_grounded_player()
    state = PlayerKnockbackState(entity)

    next_state = None
    frames = 0
    while frames < 120:
        frames += 1
        next_state = state.update(1 / 60)
        if next_state is not None:
            break

    assert next_state is not None
    assert frames <= 60
    assert abs(entity.velocity.x) < 20.0


def test_player_hurt_friction_decays_velocity_fast() -> None:
    entity = make_grounded_player()
    entity.combat.is_hurt = True  # keeps the state active across the loop
    state = PlayerHurtState(entity)

    for _ in range(60):
        state.update(1 / 60)

    assert abs(entity.velocity.x) < 20.0


def test_player_stagger_friction_decays_velocity_fast() -> None:
    entity = make_grounded_player()
    entity.stagger_timer = 1.0  # holds the state active across the loop
    state = PlayerStaggerState(entity)

    for _ in range(60):
        state.update(1 / 60)

    assert abs(entity.velocity.x) < 20.0


def test_enemy_knockback_recovers_under_one_second() -> None:
    entity = SimpleNamespace(
        velocity=pygame.Vector2(400.0, 0.0),
        on_surface={"floor": True, "left": False, "right": False},
        combat=SimpleNamespace(is_hurt=False),
    )
    state = EnemyKnockbackState(entity)

    next_state = None
    frames = 0
    while frames < 120:
        frames += 1
        next_state = state.update(1 / 60)
        if next_state is not None:
            break

    assert next_state == "idle"
    assert frames <= 60


def test_enemy_knockback_uses_central_friction_constant() -> None:
    """Friction must come from settings, not a magic number."""
    import inspect

    source = inspect.getsource(EnemyKnockbackState.__init__)
    assert "Physics.KNOCKBACK_FRICTION" not in source  # inherited default
    reaction_source = inspect.getsource(KnockbackState.__init__)
    assert "Physics.KNOCKBACK_FRICTION" in reaction_source
    assert "8.0 * delta_time" not in reaction_source


def test_player_knockback_recovers_through_hurt_when_still_hurt() -> None:
    entity = make_grounded_player()
    entity.combat.is_hurt = True
    state = PlayerKnockbackState(entity)

    next_state = None
    frames = 0
    while frames < 120:
        frames += 1
        next_state = state.update(1 / 60)
        if next_state is not None:
            break

    assert next_state == "hurt"
    assert frames <= 60