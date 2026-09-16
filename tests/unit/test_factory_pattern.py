"""Test that factory pattern is correctly used instead of direct subclass instantiation."""

import pygame
import pytest
from pygame.sprite import Group

from src.entities.enemies import ENEMY_CONFIGS, Enemy, EnemyConfig
from src.entities.enemies.factory import create_enemy, is_enemy_type


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
        for config in ENEMY_CONFIGS.values():
            assert isinstance(config, EnemyConfig)
            # Check that it has all required fields
            assert hasattr(config, "size")
            assert hasattr(config, "color")
            assert hasattr(config, "health")
            assert hasattr(config, "attacks")
            assert hasattr(config, "chase_speed")
            assert hasattr(config, "vision_range")


class TestNoDirectSubclassUsage:
    """Test that Goblin and TrainingDummy are not used directly."""

    def test_goblin_not_importable_from_enemies(self):
        """Test that Goblin cannot be imported from enemies module."""
        import importlib

        # These should NOT be available as direct subclasses.
        with pytest.raises(ImportError):
            importlib.import_module("src.entities.enemies.goblin")
            raise ImportError("Goblin must not be importable as a class")

        with pytest.raises(ImportError):
            importlib.import_module("src.entities.enemies.training_dummy")
            raise ImportError("TrainingDummy must not be importable as a class")

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


class TestPassiveEnemyFriction:
    """A no-AI enemy (dummy) must still come to a stop after a launch."""

    def _dummy_on_floor(self):
        dummy = create_enemy(
            name="dummy",
            pos=(0.0, 0.0),
            groups=Group(),
            collision_sprites=Group(),
            player_reference=None,
        )
        floor = pygame.sprite.Sprite()
        floor.rect = floor.hitbox = pygame.FRect(-2000, 48, 4000, 64)
        dummy.collision_sprites = Group(floor)
        return dummy

    def test_dummy_stops_after_heavy_knockback(self):
        """Regression: passive friction used dt twice, sliding ~40 s."""
        from src.combat.knockback import KnockbackConfig

        dummy = self._dummy_on_floor()
        dummy.receive_damage(
            10,
            source_center_x=-50.0,
            knockback=KnockbackConfig(power=(600.0, -100.0)),
        )
        assert dummy.velocity.x > 0

        for _ in range(180):  # 3 s on the ground
            dummy.update(1 / 60)

        assert dummy.velocity.x == 0.0

    def test_dummy_slows_down_quickly(self):
        """Perceptual stop (< 20 px/s) in under a second, like AI knockback."""
        from src.combat.knockback import KnockbackConfig

        dummy = self._dummy_on_floor()
        dummy.receive_damage(
            10,
            source_center_x=-50.0,
            knockback=KnockbackConfig(power=(600.0, -100.0)),
        )

        for _ in range(60):
            dummy.update(1 / 60)

        assert abs(dummy.velocity.x) < 20.0
