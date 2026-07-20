"""Test that factory pattern is correctly used instead of direct subclass instantiation."""

import pytest
import pygame
from pygame.sprite import Group

from src.entities.enemies.factory import create_enemy, is_enemy_type
from src.entities.enemies import Enemy, EnemyConfig, ENEMY_CONFIGS


class MockPlayer:
    """Mock player for testing."""
    def __init__(self):
        self.hitbox = pygame.FRect(0, 0, 48, 56)


class TestFactoryPattern:
    """Test factory pattern implementation."""

    def test_is_enemy_type_returns_true_for_valid_types(self):
        """Test that is_enemy_type returns True for valid enemy types."""
        assert is_enemy_type("goblin") is True
        assert is_enemy_type("dummy") is True
        assert is_enemy_type("slime") is True

    def test_is_enemy_type_returns_false_for_invalid_types(self):
        """Test that is_enemy_type returns False for invalid enemy types."""
        assert is_enemy_type("invalid") is False
        assert is_enemy_type("goblin2") is False
        assert is_enemy_type("") is False

    def test_create_enemy_creates_enemy_instance(self):
        """Test that create_enemy returns an Enemy instance."""
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
        
        assert isinstance(enemy, Enemy)
        assert enemy.config == ENEMY_CONFIGS["goblin"]

    def test_create_enemy_with_dummy_config(self):
        """Test creating a dummy enemy."""
        groups = Group()
        collision_sprites = Group()
        
        enemy = create_enemy(
            name="dummy",
            pos=(200, 200),
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=None,
        )
        
        assert isinstance(enemy, Enemy)
        assert enemy.config == ENEMY_CONFIGS["dummy"]
        assert enemy.player is None

    def test_create_enemy_with_slime_config(self):
        """Test creating a slime enemy."""
        groups = Group()
        collision_sprites = Group()
        player_ref = MockPlayer()
        
        enemy = create_enemy(
            name="slime",
            pos=(300, 300),
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_ref,
        )
        
        assert isinstance(enemy, Enemy)
        assert enemy.config == ENEMY_CONFIGS["slime"]

    def test_create_enemy_invalid_type_raises_keyerror(self):
        """Test that create_enemy raises KeyError for invalid enemy type."""
        groups = Group()
        collision_sprites = Group()
        
        with pytest.raises(KeyError):
            create_enemy(
                name="invalid_enemy",
                pos=(100, 100),
                groups=groups,
                collision_sprites=collision_sprites,
                player_reference=None,
            )

    def test_enemy_has_correct_attributes_from_config(self):
        """Test that enemy has correct attributes from its config."""
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
        
        config = ENEMY_CONFIGS["goblin"]
        assert enemy.chase_speed == config.chase_speed
        assert enemy.vision_range == config.vision_range
        assert enemy.attack_range == config.attack_range
        assert enemy.attack_name == config.attack_name
        assert enemy.idle_duration == config.idle_duration
        assert enemy.passive_friction == config.passive_friction
        assert enemy.pushable == config.pushable
        assert enemy.super_armor == config.super_armor

    def test_enemy_configs_are_dataclasses(self):
        """Test that all enemy configs are proper dataclasses."""
        for name, config in ENEMY_CONFIGS.items():
            assert isinstance(config, EnemyConfig)
            # Check that it has all required fields
            assert hasattr(config, 'size')
            assert hasattr(config, 'color')
            assert hasattr(config, 'health')
            assert hasattr(config, 'attacks')
            assert hasattr(config, 'chase_speed')
            assert hasattr(config, 'vision_range')


class TestNoDirectSubclassUsage:
    """Test that Goblin and TrainingDummy are not used directly."""

    def test_goblin_not_importable_from_enemies(self):
        """Test that Goblin cannot be imported from enemies module."""
        from src.entities.enemies import Enemy, create_enemy, is_enemy_type
        
        # These should NOT be available
        with pytest.raises(ImportError):
            from src.entities.enemies import Goblin
        
        with pytest.raises(ImportError):
            from src.entities.enemies import TrainingDummy

    def test_enemy_module_only_exports_factory_functions(self):
        """Test that enemies module only exports factory-related items."""
        from src.entities import enemies
        
        # Check what's in __all__
        assert "Enemy" in enemies.__all__
        assert "EnemyConfig" in enemies.__all__
        assert "ENEMY_CONFIGS" in enemies.__all__
        assert "create_enemy" in enemies.__all__
        assert "is_enemy_type" in enemies.__all__
        
        # These should NOT be in __all__
        assert "Goblin" not in enemies.__all__
        assert "TrainingDummy" not in enemies.__all__
