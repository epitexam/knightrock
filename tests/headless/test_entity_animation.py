"""Tests d'intégration de l'Animator sur les entités (Phase 2 #1)."""

import pygame

from src.entities.enemies.schema import EnemyConfig
from src.entities.player import Player
from src.states.player_states import PlayerIdleState, PlayerRunState


def test_player_starts_on_idle_animation(mock_input_manager):
    groups = pygame.sprite.Group()
    player = Player((0.0, 0.0), groups, pygame.sprite.Group(), [], mock_input_manager)

    assert player.animator is not None
    assert player.animator.current == "idle"
    # L'image initiale est encore le rectangle de couleur : la frame
    # animée n'est publiée qu'après le premier tick d'update.
    player.update(1 / 60)
    assert player.image.get_size() == (round(player.rect.width), round(player.rect.height))
    assert player.image is player.animator.surface(
        (round(player.rect.width), round(player.rect.height)), player.facing_right
    )


def test_player_switches_animation_with_state(mock_input_manager):
    groups = pygame.sprite.Group()
    player = Player((0.0, 0.0), groups, pygame.sprite.Group(), [], mock_input_manager)
    player.state_machine.add_state("run", PlayerRunState(player))
    player.state_machine.add_state("idle", PlayerIdleState(player))

    player.state_machine.change_state("run", force=True)
    player._update_animator(1 / 60)

    assert player.animator is not None
    assert player.animator.current == "run"


def test_entity_without_animator_keeps_flat_surface(mock_input_manager):
    groups = pygame.sprite.Group()
    player = Player((0.0, 0.0), groups, pygame.sprite.Group(), [], mock_input_manager)
    player.animator = None

    player.update(1 / 60)

    assert isinstance(player.image, pygame.Surface)


def test_enemy_without_animations_keeps_colored_surface():
    from src.entities.enemies.enemy import Enemy

    config = EnemyConfig(
        size=(32.0, 32.0),
        color=(200, 0, 200),
        health=50.0,
        attacks={},
        has_ai=False,
    )
    enemy = Enemy(
        (0.0, 0.0),
        pygame.sprite.Group(),
        pygame.sprite.Group(),
        None,
        config,
    )

    assert enemy.animator is None
    enemy.update(1 / 60)
    assert enemy.image.get_size() == (32, 32)
