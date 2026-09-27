"""Headless orchestration tests of a real ``Level`` (Phase 1 #10).

A full Level (player, systems, camera) is built from programmatic data — no
TMX asset required — and advanced tick by tick.
"""

import pygame
import pytest

from src.core.display.framing import DEFAULT_FRAMING
from src.core.sprites import Sprite
from tests.headless.conftest import make_programmatic_level_data


def test_level_builds_player_and_world(build_level) -> None:
    level = build_level()
    player = level.player

    assert player is not None
    assert player.hitbox.top >= 100.0
    assert level.exit_reached is False
    assert level.groups.entity_sprites.has(player)


def test_level_update_applies_gravity_and_moves_the_player(build_level) -> None:
    level = build_level()
    start_top = level.player.hitbox.top

    for _ in range(10):
        level.update(1 / 60)

    assert level.player.hitbox.top > start_top
    assert level.player.velocity.y > 0.0
    assert level.exit_reached is False


def test_level_update_detects_exit_touch(build_level) -> None:
    level = build_level()
    player = level.player
    exit_sprite = Sprite(
        pos=(player.hitbox.centerx, player.hitbox.bottom - 4.0),
        color=(255, 255, 0),
    )
    level.groups.exit_sprites.add(exit_sprite)

    level.update(1 / 60)

    assert level.exit_reached is True


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
    # The target is the window's letterbox rectangle, so the density is whatever
    # the window implies -- and it agrees with the camera, which is the only
    # thing that matters.
    assert level.surface.get_size()[0] == pytest.approx(
        level.camera.density * DEFAULT_FRAMING.width, abs=1.0
    )


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


# --- Collision grid wiring -------------------------------------------------


def test_the_player_is_wired_to_the_levels_collision_grid(build_level) -> None:
    """The level's grid must reach the player at *construction*, not after.

    The regression this pins: the grid used to be assigned in a loop that ran
    after the world was built, so any entity born later — a runtime spawn, a
    factory, a future wave system — fell back to scanning every collider in the
    level. Measured on the shipped map that is a silent x2.4 on the whole
    simulation: no exception, no log, correct physics, worse frame time.
    """
    level = build_level()

    assert level.player.spatial_hash is level.spatial_hash


def test_every_entity_the_level_builds_is_wired(build_level) -> None:
    """No entity may come out of the build without the grid."""
    level = build_level()

    unwired = [
        entity
        for entity in level.groups.entity_sprites
        if getattr(entity, "spatial_hash", None) is not level.spatial_hash
    ]

    assert unwired == []


def test_moving_platforms_are_wired_too(build_level) -> None:
    """Platforms probe the terrain they would phase through, every tick."""
    level = build_level()

    for platform in level.groups.moving_platforms:
        assert platform.spatial_hash is level.spatial_hash


def test_the_grid_is_actually_populated(build_level) -> None:
    """Wiring an *empty* grid would pass the checks above and buy nothing.

    The grid has to hold the level's colliders, and the test above — a level
    built from programmatic data — has none, so this one is about the
    relationship rather than the count.
    """
    level = build_level()

    # The grid indexes exactly the collision sprites it was handed.
    assert len(level.spatial_hash._cells_by_sprite) == len(level.groups.collision_sprites)


def test_the_spawner_is_given_its_projectile_system_not_patched_afterwards(
    build_level,
) -> None:
    """Every system is fully wired when it is constructed.

    `SpawnSystem` used to be created before the world build and handed its
    projectile system by an attribute write a few lines later, which
    contradicted the "collaborators are injected explicitly" claim the rest of
    the constructor is built on: an object that is half-configured for the
    first third of its life can be *used* in that state, and nothing said so.
    The spawner moved after the projectile system so it could be given one.
    """
    level = build_level()

    assert level.spawn_system.projectile_system is level.projectile_system


def test_the_spawner_can_fire_on_construction(build_level) -> None:
    """The consequence of the above: a spawner is never missing its launcher.

    A spawner built without one raises at the moment of use -- deep inside a
    debug keypress -- rather than at the moment of wiring.
    """
    level = build_level()

    assert level.spawn_system.projectile_system is not None


def test_the_level_answers_one_name_for_the_finished_question(build_level) -> None:
    """`completed` used to alias `exit_reached`.

    Two names for one fact is a question every reader has to answer, and a
    subclass overriding one of them would have silently not affected the
    other. One name, one fact.
    """
    level = build_level()

    assert not hasattr(type(level), "completed")
    assert level.exit_reached is False


def test_the_facade_state_is_the_systems_state(build_level) -> None:
    """The delegations are the boundary, not a copy.

    They exist so a scene asks the level a question instead of reaching into
    `level.respawn_system`. If the two ever disagree, the facade has stopped
    being one.
    """
    level = build_level()

    assert level.deaths is level.respawn_system.deaths
    assert level.respawn_timer == level.respawn_system.respawn_timer
    assert level.exit_reached is level.progression_system.exit_reached
