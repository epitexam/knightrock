"""The ``reverse`` property a level author writes on a placement.

Every ``shell`` in every shipped map carries it, and half the ``tooth`` do too,
so it is a statement about each placement and not a leftover. The world builder
used to read no per-object properties at all: it handed the type's config to the
factory unchanged, so an authored direction came out as a coin toss and a
property written seventeen times was answered with noise half the time.

Absent, false and true are three different things here, which is why the field
is a ``bool | None`` and not a ``bool``.
"""

import pygame

from src.entities.enemies.enemy import Enemy
from src.entities.enemies.factory import create_enemy
from src.entities.enemies.schema import EnemyConfig


def _config(**overrides) -> EnemyConfig:
    base = {
        "size": (36.0, 48.0),
        "color": (1, 2, 3),
        "health": 10.0,
        "attacks": {},
        "has_ai": False,
    }
    base.update(overrides)
    return EnemyConfig(**base)  # type: ignore[arg-type]


def _spawn(config: EnemyConfig) -> Enemy:
    return create_enemy(
        "goblin",
        pos=(0.0, 0.0),
        groups=(pygame.sprite.Group(),),
        collision_sprites=pygame.sprite.Group(),
        config=config,
    )


def test_an_absent_direction_keeps_the_coin_toss() -> None:
    """A type that authors nothing must not change behaviour."""
    directions = {_spawn(_config()).patrol_direction for _ in range(40)}
    assert directions == {1, -1}, f"an unauthored enemy always starts {directions}"


def test_a_false_direction_pins_the_heading_forward() -> None:
    assert all(_spawn(_config(reverse=False)).patrol_direction == 1 for _ in range(20))


def test_a_true_direction_pins_the_heading_backward() -> None:
    assert all(_spawn(_config(reverse=True)).patrol_direction == -1 for _ in range(20))


def test_the_enemy_keeps_the_rest_of_its_config() -> None:
    """Only the direction is replaced, and the config is still the type's."""
    config = _config(reverse=True)
    enemy = _spawn(config)
    assert enemy.patrol_direction == -1
    assert enemy.config.reverse is True
    assert enemy.config.health == config.health
