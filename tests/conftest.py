"""Pytest configuration and fixtures for knightrock tests."""

import pygame
import pytest
from pygame.sprite import Group

from src.core.input.input_manager import InputManager


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
