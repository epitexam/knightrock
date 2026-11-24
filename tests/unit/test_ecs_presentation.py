"""The draw adapter carries only presentation fields, not simulation state."""

import os

import pygame
import pytest

from src.core.ecs.presentation import PresentationSprite
from tests.headless.arena import arena, settle


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def test_adapter_reads_the_entity_presentation_fields() -> None:
    level, _pad, player = arena()
    settle(level)
    group = pygame.sprite.Group()
    adapter = PresentationSprite(player, group)

    assert adapter.image is player.image
    assert adapter.rect is player.rect
    assert adapter.hitbox is player.hitbox
    assert adapter.combat is player.combat
    assert adapter.faction == player.faction
    assert list(group) == [adapter]

    player.image = pygame.Surface((5, 7), pygame.SRCALPHA)
    assert adapter.image is player.image
