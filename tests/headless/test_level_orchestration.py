"""Headless orchestration tests of a real ``Level`` (Phase 1 #10).

A full Level (player, systems, camera) is built from programmatic data — no
TMX asset required — and advanced tick by tick.
"""

import pygame

from src.core.display.framing import DEFAULT_FRAMING
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

    for _ in range(130):  # ~2.17 simulated s > Respawn.DELAY_S (2.0 s)
        level.update(1 / 60)

    assert level.player.is_dead is False


def test_level_data_round_trips_through_world_builder(build_level) -> None:
    from src.core.level.level_data import LevelConfig

    level = build_level()

    assert isinstance(level.level_data.config, LevelConfig)
    assert level.level_data.pixel_width == 20 * 64
    assert level.level_data.pixel_height == 10 * 64


def test_level_draws_into_its_render_target_and_not_the_window(build_level) -> None:
    """A frame must not crash, and must land where the target is.

    This used to assert the opposite -- that the level's surface *was* the
    window -- which is the coupling the rework removed. A Level draws into a
    render target of a fixed size; the window is presented from it and nothing
    is drawn there.
    """
    level = build_level()
    player = level.player
    pygame.draw.rect(level.surface, (0, 0, 0), player.hitbox)

    assert level.draw(fps=60.0) is None

    window = pygame.display.get_surface()
    assert window is not None
    assert level.surface is not window
    assert level.surface.get_size() == DEFAULT_FRAMING.viewport_size(level.camera.scale)


def test_programmatic_level_data_has_no_colliders(build_level) -> None:
    level = build_level()

    assert len(level.groups.collision_sprites) == 0

    # An empty level: the build only produces the player, no scenery.
    assert len(level.groups.all_sprites) >= 1


def test_make_programmatic_level_data_is_idempotent() -> None:
    first = make_programmatic_level_data()
    second = make_programmatic_level_data()

    assert len(first.object_layers) == len(second.object_layers)
    assert first.object_layers["Entities"].objects[0].name == "player"
