"""The shipped level must contain enemies.

This is the content test the repository could not have while ``assets/`` was
ignored: every other combat test ran against hand-built doubles, and the real
level had never once been loaded by a test. It had never been loaded at all --
the objects the maps declare as ``shell`` and ``tooth`` named types nothing in
``ENEMY_CONFIGS`` knew, so the world builder filed them as decorative sprites
and the game shipped a hack-and-slash with nothing to slash. Twelve of them in
``1.tmx`` alone.

Skipped when the maps are absent, which is the CI case: without them there is
nothing to check *against*, and the rest of the suite must still run. The maps
are meant to be tracked, so if this test is skipping on a machine that has
them, that is the finding.
"""

import os

import pygame
import pytest

from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.entities.enemies.configs import ENEMY_CONFIGS
from src.entities.enemies.enemy import Enemy

ASSETS_PRESENT = os.path.isdir(
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "data")
)


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


@pytest.fixture(scope="module")
def built_enemies() -> list[Enemy]:
    from src.core.input.input_manager import InputManager
    from src.core.level.level import Level

    surface = pygame.Surface((1280, 720))
    level = Level(surface, LevelManager(LEVEL_PATHS).get(0), InputManager())
    return [sprite for sprite in level.groups.entity_sprites if isinstance(sprite, Enemy)]


@pytest.mark.skipif(not ASSETS_PRESENT, reason="assets/ is git-ignored and absent")
def test_the_shipped_level_contains_enemies(built_enemies: list[Enemy]) -> None:
    """A level that loads without one is a level nothing tests the combat against."""
    assert len(built_enemies) > 0


@pytest.mark.skipif(not ASSETS_PRESENT, reason="assets/ is git-ignored and absent")
def test_every_enemy_the_level_declares_is_a_registered_type(built_enemies: list[Enemy]) -> None:
    """A name the builder cannot resolve becomes a decorative sprite.

    That is what happened to ``shell`` and ``tooth``: the objects were placed,
    the art was drawn, and nothing in the level could be damaged. Each enemy
    built here carries a config, which is only true for a resolved name.
    """
    known = {id(config) for config in ENEMY_CONFIGS.values()}
    for enemy in built_enemies:
        assert id(enemy.config) in known, f"{enemy} was built without a registered enemy config"


@pytest.mark.skipif(not ASSETS_PRESENT, reason="assets/ is git-ignored and absent")
def test_the_enemies_carry_the_art_their_config_points_at(built_enemies: list[Enemy]) -> None:
    """An animation directory that does not exist draws nothing.

    The art for ``shell`` and ``tooth`` shipped long before their configs did,
    so both directions of the mismatch were possible: a config naming art that
    is not there, or art with no config naming it.
    """
    for enemy in built_enemies:
        for state, directory in enemy.config.animations.items():
            assert os.path.isdir(directory), f"{state} animation {directory} is missing"
            assert any(name.endswith(".png") for name in os.listdir(directory)), (
                f"{state} animation {directory} holds no frames"
            )
