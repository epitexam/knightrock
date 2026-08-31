"""BUG-03: hazards (saw/spike/floor_spike) must deal damage on overlap."""

from types import SimpleNamespace
from unittest.mock import Mock

import pygame

from src.physics.hazard_damage import HazardDamageSystem


def make_entity(hitbox: pygame.FRect, *, is_dead: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        is_dead=is_dead,
        hitbox=hitbox,
        velocity=pygame.Vector2(0, 0),
        receive_damage=Mock(return_value=None),
    )


class FakeHazard:
    def __init__(
        self,
        rect: pygame.FRect,
        *,
        damage: float = 25.0,
        knockback=None,
    ) -> None:
        self.rect = rect
        self.damage = damage
        self.knockback = knockback


def test_hazard_applies_configured_damage() -> None:
    entity = make_entity(pygame.FRect(0, 0, 40, 40))
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    entity.receive_damage.assert_called_once()
    kwargs = entity.receive_damage.call_args.kwargs
    assert kwargs["amount"] == 25.0
    assert kwargs["interrupt"] is False
    assert kwargs["source_center_x"] == pygame.FRect(10, 10, 64, 64).centerx


def test_hazard_uses_default_damage_when_unspecified() -> None:
    entity = make_entity(pygame.FRect(0, 0, 40, 40))
    hazard = SimpleNamespace(rect=pygame.FRect(10, 10, 64, 64))
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    assert entity.receive_damage.call_args.kwargs["amount"] == (
        HazardDamageSystem.DEFAULT_DAMAGE
    )


def test_hazard_ignores_non_overlapping_entities() -> None:
    entity = make_entity(pygame.FRect(600, 600, 40, 40))
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    entity.receive_damage.assert_not_called()


def test_hazard_ignores_dead_entities() -> None:
    entity = make_entity(pygame.FRect(0, 0, 40, 40), is_dead=True)
    hazard = FakeHazard(pygame.FRect(10, 10, 64, 64), damage=25.0)
    system = HazardDamageSystem()

    system.process([entity], [hazard])

    entity.receive_damage.assert_not_called()


def test_hazard_defaults_are_non_zero_threat() -> None:
    assert HazardDamageSystem.DEFAULT_DAMAGE > 0
    assert HazardDamageSystem.DEFAULT_KNOCKBACK.power != (0.0, 0.0)