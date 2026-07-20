"""Test type annotations and consistency across Entity, Enemy, and Player."""

import pytest
import pygame
from pygame.math import Vector2
from pygame.sprite import Group

from src.entities.entity import Entity
from src.entities.player import Player, DEFAULT_PLAYER_CONFIG
from src.entities.enemies.factory import create_enemy
from src.entities.enemies.schema import EnemyConfig


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


class TestPosTypeAnnotations:
    """Test that pos parameter accepts Sequence[float] | Vector2 consistently."""

    def test_entity_accepts_sequence_pos(self):
        """Test that Entity accepts Sequence[float] for pos."""
        groups = Group()
        collision_sprites = Group()
        
        # Test with list
        entity1 = Entity(
            pos=[100, 100],
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
        )
        assert entity1.hitbox.centerx == 100
        assert entity1.hitbox.centery == 100
        
        # Test with tuple
        entity2 = Entity(
            pos=(200, 200),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
        )
        assert entity2.hitbox.centerx == 200
        assert entity2.hitbox.centery == 200

    def test_entity_accepts_vector2_pos(self):
        """Test that Entity accepts Vector2 for pos."""
        groups = Group()
        collision_sprites = Group()
        
        entity = Entity(
            pos=Vector2(300, 300),
            size=(48, 56),
            color=(0, 255, 0),
            groups=groups,
            collision_sprites=collision_sprites,
        )
        assert entity.hitbox.centerx == 300
        assert entity.hitbox.centery == 300

    def test_enemy_accepts_sequence_pos(self):
        """Test that Enemy accepts Sequence[float] for pos."""
        groups = Group()
        collision_sprites = Group()
        player_ref = MockPlayer()
        
        # Test with list
        enemy1 = create_enemy(
            name="goblin",
            pos=[100, 100],
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_ref,
        )
        assert enemy1.hitbox.centerx == 100
        
        # Test with tuple
        enemy2 = create_enemy(
            name="goblin",
            pos=(200, 200),
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_ref,
        )
        assert enemy2.hitbox.centerx == 200

    def test_enemy_accepts_vector2_pos(self):
        """Test that Enemy accepts Vector2 for pos."""
        groups = Group()
        collision_sprites = Group()
        player_ref = MockPlayer()
        
        enemy = create_enemy(
            name="goblin",
            pos=Vector2(300, 300),
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_ref,
        )
        assert enemy.hitbox.centerx == 300
        assert enemy.hitbox.centery == 300

    def test_player_accepts_tuple_pos(self):
        """Test that Player accepts tuple[float, float] for pos."""
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
        assert player.hitbox.centerx == 100
        assert player.hitbox.centery == 100

    def test_player_accepts_vector2_pos(self):
        """Test that Player accepts Vector2 for pos."""
        groups = Group()
        collision_sprites = Group()
        moving_platforms = []
        input_manager = MockInputManager()
        
        player = Player(
            pos=Vector2(200, 200),
            groups=groups,
            collision_sprites=collision_sprites,
            moving_platforms=moving_platforms,
            input_manager=input_manager,
        )
        assert player.hitbox.centerx == 200
        assert player.hitbox.centery == 200


class TestPlayerReferenceTyping:
    """Test that player_reference uses proper Protocol typing."""

    def test_enemy_player_reference_has_hitbox(self):
        """Test that Enemy player reference has hitbox attribute."""
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
        
        assert enemy.player is player_ref
        assert hasattr(enemy.player, 'hitbox')
        assert isinstance(enemy.player.hitbox, pygame.FRect)

    def test_enemy_player_reference_can_be_none(self):
        """Test that Enemy player reference can be None."""
        groups = Group()
        collision_sprites = Group()
        
        enemy = create_enemy(
            name="dummy",
            pos=(100, 100),
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=None,
        )
        
        assert enemy.player is None


class TestClassAnnotations:
    """Test that classes have proper type annotations."""

    def test_entity_has_class_annotations(self):
        """Test that Entity has class-level type annotations."""
        # Check that Entity has type annotations
        assert hasattr(Entity, '__annotations__')
        annotations = Entity.__annotations__
        
        # Should have some annotations
        assert len(annotations) > 0
        
        # Check for specific annotations
        assert 'hitbox' in annotations
        assert 'velocity' in annotations
        assert 'on_surface' in annotations

    def test_player_has_class_annotations(self):
        """Test that Player has class-level type annotations."""
        assert hasattr(Player, '__annotations__')
        annotations = Player.__annotations__
        
        # Should have many annotations
        assert len(annotations) > 0
        
        # Check for specific annotations
        assert 'input_manager' in annotations
        assert 'speed' in annotations
        assert 'floor_control' in annotations
        assert 'health' in annotations

    def test_enemy_has_class_annotations(self):
        """Test that Enemy has class-level type annotations."""
        from src.entities.enemies.enemy import Enemy
        
        assert hasattr(Enemy, '__annotations__')
        annotations = Enemy.__annotations__
        
        # Should have annotations
        assert len(annotations) > 0
        
        # Check for specific annotations
        assert 'config' in annotations
        assert 'player' in annotations
        assert 'chase_speed' in annotations
        assert 'vision_range' in annotations


class TestPrivateVariables:
    """Test that private variables use _ prefix consistently."""

    def test_player_private_variables_have_underscore_prefix(self):
        """Test that Player private variables have _ prefix."""
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
        
        # Check that private variables exist and have _ prefix
        assert hasattr(player, '_dash_duration_timer')
        assert hasattr(player, '_original_hitbox_width')
        assert hasattr(player, '_dash_requested')
        
        # Check that input state variables are private
        assert hasattr(player, '_space_held')
        assert hasattr(player, '_left_held')
        assert hasattr(player, '_right_held')
        assert hasattr(player, '_block_held')

    def test_player_public_variables_no_underscore(self):
        """Test that Player public variables don't have _ prefix."""
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
        
        # Check that public variables don't have _ prefix
        assert hasattr(player, 'speed')
        assert hasattr(player, 'health')
        assert hasattr(player, 'input_manager')
        assert hasattr(player, 'moving_platforms')
