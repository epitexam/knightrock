"""Tests for the Vitals component (ARCH-02 extraction) and its Entity delegation."""

from unittest.mock import Mock

from pygame.math import Vector2
from pygame.sprite import Group

from src.entities.entity import Entity
from src.entities.vitals import Vitals


def make_vitals(**kwargs) -> Vitals:
    return Vitals(**kwargs)


def test_health_is_clamped_to_valid_range() -> None:
    vitals = make_vitals(health=80.0, max_health=100.0)
    vitals.health = 500.0
    assert vitals.health == 100.0
    vitals.health = -10.0
    assert vitals.health == 0.0


def test_health_zero_triggers_death_and_callback() -> None:
    on_death = Mock()
    vitals = make_vitals(health=10.0, on_death=on_death)
    vitals.health = 0.0
    assert vitals.is_dead is True
    on_death.assert_called_once_with()


def test_max_health_never_below_one() -> None:
    vitals = make_vitals(max_health=100.0)
    vitals.max_health = -5.0
    assert vitals.max_health == 1.0


def test_can_receive_damage_blocks_dead_and_invincible() -> None:
    vitals = make_vitals()
    assert vitals.can_receive_damage() is True
    vitals.is_dead = True
    assert vitals.can_receive_damage() is False
    vitals.is_dead = False
    vitals.invincibility_timer = 0.5
    assert vitals.can_receive_damage() is False


def test_apply_damage_returns_actual_damage() -> None:
    vitals = make_vitals(health=50.0, max_health=100.0)
    dealt = vitals.apply_damage(20.0)
    assert dealt == 20.0
    assert vitals.health == 30.0


def test_tick_timers_decays_without_going_below_zero() -> None:
    vitals = make_vitals()
    vitals.stagger_timer = 0.5
    vitals.invincibility_timer = 0.2
    vitals.tick_timers(1.0)
    assert vitals.stagger_timer == 0.0
    assert vitals.invincibility_timer == 0.0


def test_reset_restores_health_and_clears_status() -> None:
    on_death = Mock()
    vitals = make_vitals(health=100.0, max_health=100.0, on_death=on_death)
    vitals.health = 30.0
    vitals.stagger_timer = 0.5
    vitals.super_armor = True
    vitals.super_armor_count = 2
    vitals.invincibility_timer = 0.5

    vitals.reset()

    assert vitals.health == 100.0
    assert vitals.is_dead is False
    assert vitals.stagger_timer == 0.0
    assert vitals.super_armor is False
    assert vitals.super_armor_count == 0
    assert vitals.invincibility_timer == 0.0


def test_entity_delegates_health_and_status_to_vitals() -> None:
    entity = Entity(
        pos=(0.0, 0.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
        health=75.0,
        max_health=100.0,
    )
    assert entity.health == 75.0
    assert entity.max_health == 100.0
    assert entity.is_dead is False

    entity.health = 10.0
    assert entity.vitals.health == 10.0
    assert entity.vitals.is_dead is False

    entity.health = 0.0
    assert entity.is_dead is True
    assert entity.vitals.is_dead is True


def test_entity_death_resets_combat_via_callback() -> None:
    entity = Entity(
        pos=(0.0, 0.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
        health=10.0,
    )
    entity.combat.reset = Mock()
    entity.health = 0.0
    entity.combat.reset.assert_called_once_with()


def test_entity_spawn_pos_is_delegated() -> None:
    entity = Entity(
        pos=(5.0, 9.0),
        size=(40.0, 40.0),
        color=(255, 255, 255),
        groups=Group(),
        collision_sprites=Group(),
    )
    assert entity.spawn_pos == Vector2(5.0, 9.0)
    assert entity.vitals.spawn_pos == Vector2(5.0, 9.0)