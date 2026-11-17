"""Pytest configuration and fixtures for knightrock tests."""

import pygame
import pytest
from pygame.sprite import Group

from src.core.input.input_manager import InputManager
from src.core.paths import PROJECT_ROOT

#: `assets/` is git-ignored: a fresh checkout (and therefore CI) has fonts and
#: sounds but no TMX maps or sprite art. Tests that build a real Player/Level
#: need those files; gate them with this one marker so they report SKIPPED with
#: an explicit reason instead of failing to import or raising FileNotFoundError.
ASSETS_PRESENT = (PROJECT_ROOT / "assets/graphics/player/idle").is_dir() and (
    PROJECT_ROOT / "assets/data/levels/1.tmx"
).is_file()

requires_assets = pytest.mark.skipif(
    not ASSETS_PRESENT,
    reason=(
        "git-ignored assets/ absent on a fresh checkout: "
        "this test needs real art or TMX (run with the assets present)"
    ),
)


@pytest.fixture
def mock_player():
    """Fixture providing a mock player with hitbox."""

    class MockPlayer:
        def __init__(self):
            self.hitbox = pygame.FRect(0, 0, 48, 56)

    return MockPlayer()


@pytest.fixture
def mock_input_manager():
    return InputManager()


@pytest.fixture
def groups():
    """Fixture providing pygame sprite groups."""
    return Group(), Group()


@pytest.fixture
def empty_groups():
    """Fixture providing empty pygame sprite groups."""
    return Group(), Group()
