"""Behavioral tests for damage and hit reaction resolution."""

from __future__ import annotations

import pygame
from pygame.sprite import Group

from src.combat.combatant_protocol import DamageResult
from src.combat.damage_types import DamageType
from src.combat.frame_data import HitProperties
from src.combat.hit_resolver import HitResolver
from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings
from src.entities.entity import Entity
from src.entities.player import Player
from tests.unit.helpers import AttackerStub, InputStub, SpyCombat, SpyStateMachine
from tests.unit.helpers import make_entity as build_entity


def make_entity(*, health: float = 100.0, invincibility: float = 0.0) -> Entity:
    """Build an entity instrumented with spy combat/state-machine hooks."""
    entity = build_entity(health=health, invincibility=invincibility)
    entity.combat = SpyCombat()  # type: ignore[assignment]
    entity.state_machine = SpyStateMachine()  # type: ignore[assignment]
    return entity


def test_block_prevents_damage_and_all_hit_reactions() -> None:
    player = Player(
        pos=(100.0, 100.0),
        groups=Group(),
        collision_sprites=Group(),
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    player.state_machine.current_state_name = "block"
    initial_health = player.health
    initial_stamina = player.block.block_stamina

    result = HitResolver.resolve(
        AttackerStub(centerx=80.0),  # type: ignore[arg-type]
        player,
        HitProperties(
            damage=10,
            knockback=KnockbackConfig(power=(200.0, -100.0)),
            stagger=0.25,
            is_finisher=True,
        ),
    )

    assert result == DamageResult(blocked=True)
    assert player.health == initial_health
    assert player.block.block_stamina < initial_stamina
    assert player.velocity.x == 60.0
    assert player.combat.is_hurt is False
    assert player.stagger_timer == 0.0


def test_invincibility_does_not_interrupt_or_apply_knockback() -> None:
    target = make_entity(invincibility=0.2)
    target.invincibility_timer = 0.1
    combat = target.combat

    result = HitResolver.resolve(
        AttackerStub(centerx=80.0),  # type: ignore[arg-type]
        target,
        HitProperties(
            damage=20,
            knockback=KnockbackConfig(power=(500.0, -500.0)),
            stagger=0.3,
        ),
    )

    assert result.applied is False
    assert target.health == 100.0
    assert target.velocity == pygame.Vector2(0.0, 0.0)
    assert combat.hit_interrupts == []  # type: ignore[union-attr]
    assert target.stagger_timer == 0.0


def test_vertical_uppercut_triggers_knockback_without_hurt_conflict() -> None:
    target = make_entity()

    result = HitResolver.resolve(
        AttackerStub(centerx=target.hitbox.centerx),  # type: ignore[arg-type]
        target,
        HitProperties(
            damage=12,
            knockback=KnockbackConfig(power=(0.0, -800.0)),
        ),
    )

    assert result.heavy_knockback is True
    assert target.velocity.y == -800.0
    assert target.state_machine.changes[-1][0] == "knockback"  # type: ignore[union-attr]
    assert target.combat.is_hurt is False


def test_heavy_knockback_threshold_is_inclusive_and_uses_magnitude() -> None:
    target = make_entity()

    at_threshold = target.receive_damage(
        1.0,
        knockback=KnockbackConfig(power=(0.0, -CombatSettings.HEAVY_KNOCKBACK_THRESHOLD)),
    )

    assert at_threshold.heavy_knockback is True
    assert target.state_machine.changes[-1][0] == "knockback"  # type: ignore[union-attr]

    diagonal_target = make_entity()
    diagonal = diagonal_target.receive_damage(
        1.0,
        knockback=KnockbackConfig(power=(300.0, -300.0)),
    )

    assert diagonal.heavy_knockback is True


def test_finisher_is_atomic_even_when_damage_starts_invincibility() -> None:
    target = make_entity(health=25.0, invincibility=0.2)

    result = HitResolver.resolve(
        AttackerStub(centerx=80.0),  # type: ignore[arg-type]
        target,
        HitProperties(
            damage=10,
            is_finisher=True,
            knockback=KnockbackConfig(power=(100.0, 0.0)),
        ),
    )

    assert result.killed is True
    assert result.actual_damage == 25.0
    assert target.health == 0.0


def test_resolver_reports_and_applies_actual_damage() -> None:
    target = make_entity(health=15.0)

    result = HitResolver.resolve(
        AttackerStub(centerx=80.0),  # type: ignore[arg-type]
        target,
        HitProperties(
            damage=20,
            damage_type=DamageType.SLASH,
            knockback=KnockbackConfig(power=(100.0, -50.0)),
        ),
    )

    assert result.applied is True
    assert result.actual_damage == 15.0
    assert result.killed is True
    assert target.health == 0.0
    assert target.combat.hit_interrupts == []  # type: ignore[union-attr]
