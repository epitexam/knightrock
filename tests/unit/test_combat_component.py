"""Test combat component initialization and the fix for the combat=None antipattern."""

import pytest
import pygame
from pygame.sprite import Group

from src.entities.enemies.factory import create_enemy
from src.entities.player import Player, DEFAULT_PLAYER_CONFIG
from src.combat.combat_component import CombatComponent, NullCombatComponent


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
        self.attack1_just_pressed = False
        self.attack2_just_pressed = False
        self.attack2_just_released = False


class MockPlayer:
    """Mock player for testing."""
    def __init__(self):
        self.hitbox = pygame.FRect(0, 0, 48, 56)


class TestCombatComponentInitialization:
    """Test that combat components are properly initialized."""

    def test_enemy_has_combat_component_not_null(self):
        """Test that Enemy has a real CombatComponent, not NullCombatComponent."""
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
        
        # Enemy should have a real CombatComponent, not NullCombatComponent
        assert isinstance(enemy.combat, CombatComponent)
        assert not isinstance(enemy.combat, NullCombatComponent)
        
        # Combat component should be properly configured
        assert hasattr(enemy.combat, 'state')
        assert hasattr(enemy.combat, 'hitbox')
        assert hasattr(enemy.combat, 'combo')
        assert hasattr(enemy.combat, 'charging')

    def test_player_has_combat_component_not_null(self):
        """Test that Player has a real CombatComponent, not NullCombatComponent."""
        groups = Group()
        collision_sprites = Group()
        moving_platforms = []
        input_manager = MockInputManager()
        
        player = Player(
            pos=(100, 100),
            groups=groups,
            collision_sprites=collision_sprites,
            moving_platforms=moving_platforms,
            input_manager=input_manager,
        )
        
        # Player should have a real CombatComponent, not NullCombatComponent
        assert isinstance(player.combat, CombatComponent)
        assert not isinstance(player.combat, NullCombatComponent)
        
        # Combat component should be properly configured
        assert hasattr(player.combat, 'state')
        assert hasattr(player.combat, 'hitbox')
        assert hasattr(player.combat, 'combo')
        assert hasattr(player.combat, 'charging')

    def test_combat_component_has_attacks_loaded(self):
        """Test that combat component has attacks loaded from config."""
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
        
        # Combat component should have attacks loaded
        assert hasattr(enemy.combat, '_attacks')
        # Goblin config has GOBLIN_ATTACKS
        assert len(enemy.combat._attacks) > 0

    def test_player_combat_component_has_attacks_loaded(self):
        """Test that player combat component has attacks loaded."""
        groups = Group()
        collision_sprites = Group()
        moving_platforms = []
        input_manager = MockInputManager()
        
        player = Player(
            pos=(100, 100),
            groups=groups,
            collision_sprites=collision_sprites,
            moving_platforms=moving_platforms,
            input_manager=input_manager,
        )
        
        # Combat component should have attacks loaded from PLAYER_ATTACKS
        assert hasattr(player.combat, '_attacks')
        assert len(player.combat._attacks) > 0


class TestNoNullCombatComponentWaste:
    """Test that no NullCombatComponent is created and discarded."""

    def test_entity_with_attacks_no_null_combat(self):
        """Test that Entity with attacks doesn't create NullCombatComponent."""
        from src.entities.entity import Entity
        from src.combat.attack_data import PLAYER_ATTACKS
        
        groups = Group()
        collision_sprites = Group()
        
        # Create entity with attacks
        entity = Entity(
            pos=(100, 100),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
            attacks=PLAYER_ATTACKS,
        )
        
        # Should have CombatComponent, not NullCombatComponent
        assert isinstance(entity.combat, CombatComponent)
        assert not isinstance(entity.combat, NullCombatComponent)

    def test_entity_without_attacks_has_null_combat(self):
        """Test that Entity without attacks has NullCombatComponent."""
        from src.entities.entity import Entity
        
        groups = Group()
        collision_sprites = Group()
        
        # Create entity without attacks
        entity = Entity(
            pos=(100, 100),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
        )
        
        # Should have NullCombatComponent
        assert isinstance(entity.combat, NullCombatComponent)
