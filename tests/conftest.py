"""Pytest configuration and fixtures for knightrock tests."""

import pytest
import pygame
from pygame.sprite import Group


@pytest.fixture
def mock_player():
    """Fixture providing a mock player with hitbox."""
    class MockPlayer:
        def __init__(self):
            self.hitbox = pygame.FRect(0, 0, 48, 56)
    
    return MockPlayer()


@pytest.fixture
def mock_input_manager():
    """Fixture providing a mock input manager."""
    class MockInputManager:
        def __init__(self):
            self.move_axis = 0.0
            self.left_held = False
            self.right_held = False
            self.block_held = False
            self.jump_just_pressed = False
            self.dash_just_pressed = False
            self.reset_just_pressed = False
            self.attack1_just_pressed = False
            self.attack2_just_pressed = False
            self.attack2_just_released = False
    
    return MockInputManager()


@pytest.fixture
def groups():
    """Fixture providing pygame sprite groups."""
    return Group(), Group()


@pytest.fixture
def empty_groups():
    """Fixture providing empty pygame sprite groups."""
    return Group(), Group()
