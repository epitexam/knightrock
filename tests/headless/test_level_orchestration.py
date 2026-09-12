"""Tests d'orchestration headless d'un vrai ``Level`` (Phase 1 #10).

Un Level complet (joueur, systèmes, camera) est construit à partir de
données programmatiques — aucun asset TMX requis — et avancé tick par tick.
"""

import pygame

from src.core.sprites import Sprite
from tests.headless.conftest import make_programmatic_level_data


def test_level_builds_player_and_world(build_level) -> None:
    level = build_level()
    player = level.player

    assert player is not None
    assert player.hitbox.top >= 100.0
    assert level.completed is False
    assert level.groups.entity_sprites.has(player)


def test_level_update_applies_gravity_and_moves_the_player(build_level) -> None:
    level = build_level()
    start_top = level.player.hitbox.top

    for _ in range(10):
        level.update(1 / 60)

    assert level.player.hitbox.top > start_top
    assert level.player.velocity.y > 0.0
    assert level.completed is False


def test_level_update_detects_exit_touch(build_level) -> None:
    level = build_level()
    player = level.player
    exit_sprite = Sprite(
        pos=(player.hitbox.centerx, player.hitbox.bottom - 4.0),
        color=(255, 255, 0),
    )
    level.groups.exit_sprites.add(exit_sprite)

    level.update(1 / 60)

    assert level.completed is True


def test_level_respawns_the_player_after_death_delay(build_level) -> None:
    level = build_level()
    level.player.die()
    assert level.player.is_dead

    for _ in range(130):  # ~2,17 s simulées > Respawn.DELAY_S (2,0 s)
        level.update(1 / 60)

    assert level.player.is_dead is False


def test_level_data_round_trips_through_world_builder(build_level) -> None:
    from src.core.level.level_data import LevelConfig

    level = build_level()

    assert isinstance(level.level_data.config, LevelConfig)
    assert level.level_data.pixel_width == 20 * 64
    assert level.level_data.pixel_height == 10 * 64


def test_level_supports_draw_pass(build_level) -> None:
    """Le rendu plein écran ne doit pas crasher (SDL dummy)."""
    level = build_level()
    player = level.player
    pygame.draw.rect(level.display_surface, (0, 0, 0), player.hitbox)

    level.draw(fps=60.0)

    assert level.display_surface is pygame.display.get_surface()


def test_programmatic_level_data_has_no_colliders(build_level) -> None:
    level = build_level()

    assert len(level.groups.collision_sprites) == 0

    # Un niveau vide : le build ne produit que le joueur, pas de décor.
    assert len(level.groups.all_sprites) >= 1


def test_make_programmatic_level_data_is_idempotent() -> None:
    first = make_programmatic_level_data()
    second = make_programmatic_level_data()

    assert len(first.object_layers) == len(second.object_layers)
    assert first.object_layers["Entities"].objects[0].name == "player"
