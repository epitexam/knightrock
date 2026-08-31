"""Test reset_position functionality and state machine reset."""

import pytest
import pygame
from pygame.sprite import Group

from src.entities.enemies.factory import create_enemy
from src.entities.player import Player
from src.entities.entity import Entity


class MockInputManager:
    """Mock input manager for testing."""
    def __init__(self):
        self.move_axis = 0.0
        self.left_held = False
        self.right_held = False
        self.block_held = False
        self.jump_just_pressed = False
        self.dash_just_pressed = False
        self.reset_just_pressed = False


class MockPlayer:
    """Mock player for testing."""
    def __init__(self):
        self.hitbox = pygame.FRect(0, 0, 48, 56)


class TestResetPosition:
    """Test reset_position functionality."""

    def test_entity_reset_position_resets_position(self):
        """Test that Entity.reset_position resets to spawn position."""
        groups = Group()
        collision_sprites = Group()
        
        entity = Entity(
            pos=(100, 100),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
            spawn_pos=(100, 100),
        )
        
        # Move entity
        entity.hitbox.x = 200
        entity.hitbox.y = 200
        entity.velocity.x = 100
        entity.velocity.y = 50
        
        # Reset position
        entity.reset_position()
        
        # Check that position is reset
        assert entity.hitbox.centerx == 100
        assert entity.hitbox.centery == 100
        
        # Check that velocity is reset
        assert entity.velocity.x == 0
        assert entity.velocity.y == 0

    def test_entity_reset_position_resets_health(self):
        """Test that Entity.reset_position resets health."""
        groups = Group()
        collision_sprites = Group()
        
        entity = Entity(
            pos=(100, 100),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
            health=50.0,
            max_health=100.0,
        )
        
        # Damage entity
        entity.health = 25.0
        
        # Reset position
        entity.reset_position()
        
        # Check that health is reset
        assert entity.health == 100.0

    def test_entity_reset_position_resets_dead_state(self):
        """Test that Entity.reset_position resets dead state."""
        groups = Group()
        collision_sprites = Group()
        
        entity = Entity(
            pos=(100, 100),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
            health=1.0,
        )
        
        # Kill entity
        entity.health = 0
        
        # Check that entity is dead
        assert entity.is_dead is True
        
        # Reset position
        entity.reset_position()
        
        # Check that entity is no longer dead
        assert entity.is_dead is False

    def test_entity_reset_position_calls_state_machine_change(self):
        """Test that Entity.reset_position changes state machine to idle."""
        from src.states.state_machine import StateMachine
        from src.states.null_state_machine import NullStateMachine
        
        groups = Group()
        collision_sprites = Group()
        
        entity = Entity(
            pos=(100, 100),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
        )
        
        # Entity should have NullStateMachine by default
        assert isinstance(entity.state_machine, NullStateMachine)
        
        # Reset position should not fail even with NullStateMachine
        entity.reset_position()

    def test_enemy_reset_position_resets_to_spawn(self):
        """Test that Enemy.reset_position resets to spawn position."""
        groups = Group()
        collision_sprites = Group()
        player_ref = MockPlayer()
        
        enemy = create_enemy(
            name="goblin",
            pos=(100, 100),
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_ref,
        )
        
        # Move enemy
        enemy.hitbox.x = 200
        enemy.hitbox.y = 200
        enemy.velocity.x = 100
        
        # Reset position
        enemy.reset_position()
        
        # Check that position is reset
        assert enemy.hitbox.centerx == 100
        assert enemy.hitbox.centery == 100
        assert enemy.velocity.x == 0

    def test_enemy_reset_position_resets_state_machine(self):
        """Test that Enemy.reset_position resets state machine to idle."""
        groups = Group()
        collision_sprites = Group()
        player_ref = MockPlayer()
        
        enemy = create_enemy(
            name="goblin",
            pos=(100, 100),
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_ref,
        )
        
        # Enemy should have a state machine
        assert hasattr(enemy, 'state_machine')
        assert enemy.state_machine.current_state_name == "idle"
        
        # Reset position
        enemy.reset_position()
        
        # State machine should be reset to idle
        assert enemy.state_machine.current_state_name == "idle"

    def test_player_reset_position_resets_all_state(self):
        """Test that Player.reset_position resets all player-specific state."""
        groups = Group()
        collision_sprites = Group()
        moving_platforms = []
        input_manager = MockInputManager()
        
        player = Player(
            pos=(100, 100),
            groups=groups,
            collision_sprites=collision_sprites,
            moving_platforms=moving_platforms,
            input_manager=input_manager,  # type: ignore[arg-type]
        )
        
        # Modify player state
        player.hitbox.x = 200
        player.velocity.x = 100
        player.health = 50
        player.dash.charges = 0
        player.block.block_stamina = 0
        
        # Reset position
        player.reset_position()
        
        # Check that position and velocity are reset
        assert player.hitbox.centerx == 100
        assert player.velocity.x == 0
        
        # Check that health is reset
        assert player.health == player.max_health
        
        # Check that dash charges are reset
        assert player.dash.charges == player.dash.max_charges
        
        # Check that block stamina is reset
        assert player.block.block_stamina == player.block.max_block_stamina

    def test_player_reset_position_resets_state_machine(self):
        """Test that Player.reset_position resets state machine to idle."""
        groups = Group()
        collision_sprites = Group()
        moving_platforms = []
        input_manager = MockInputManager()
        
        player = Player(
            pos=(100, 100),
            groups=groups,
            collision_sprites=collision_sprites,
            moving_platforms=moving_platforms,
            input_manager=input_manager,  # type: ignore[arg-type]
        )
        
        # Player should have a state machine
        assert hasattr(player, 'state_machine')
        
        # Reset position
        player.reset_position()
        
        # State machine should be reset to idle
        assert player.state_machine.current_state_name == "idle"
