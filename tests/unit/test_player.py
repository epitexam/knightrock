import pytest
import pygame
from src.entities.player import Player
from src.core.input.input_manager import InputManager
from src.core.settings import World

@pytest.fixture
def player_setup():
    pygame.init()
    pygame.display.set_mode((100, 100))
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    input_manager = InputManager()
    
    player = Player(
        pos=(0, 0),
        groups=groups,
        collision_sprites=collision_sprites,
        moving_platforms=[],
        input_manager=input_manager
    )
    return player, input_manager

def test_player_initialization(player_setup):
    player, _ = player_setup
    assert player.health == player.max_health
    assert player.state_machine.current_state_name == "idle"

def test_player_dash_charges(player_setup):
    player, _ = player_setup
    assert player.dash.charges == player.dash.max_charges
    
    # Dash request should be allowed in idle/fall state
    player.dash.requested = True
    assert player._can_dash() == True
