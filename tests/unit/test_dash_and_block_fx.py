"""The block, drawn: an animated shield that opens outward on the side the blow
came from and throws sparks off its face."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.sprite import Group

from src.core.fx.particles import ShieldArcParticle
from src.core.fx.spawners import spawn_guard_arc


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def _entity(facing: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        hitbox=pygame.FRect(100, 100, 40, 48),
        velocity=pygame.math.Vector2(0.0, 0.0),
        facing_right=facing,
    )


def test_the_shield_opens_outward_as_it_lives() -> None:
    shield = spawn_guard_arc(Group(), _entity())
    assert isinstance(shield, ShieldArcParticle)
    first = pygame.mask.from_surface(shield.image).count()
    shield.update(shield.max_ttl * 0.5)

    assert shield.age > 0.0
    assert pygame.mask.from_surface(shield.image).count() != first, "it moves, it is not a stamp"


def test_the_shield_and_its_sparks_are_on_the_side_of_the_blow() -> None:
    shield = spawn_guard_arc(Group(), _entity(facing=True))
    assert shield is not None
    shield.update(shield.max_ttl * 0.4)
    image = shield.image
    width, height = image.get_size()
    left = sum(1 for x in range(width // 2) for y in range(height) if image.get_at((x, y))[3])
    right = sum(
        1 for x in range(width // 2, width) for y in range(height) if image.get_at((x, y))[3]
    )

    assert right > left * 2
