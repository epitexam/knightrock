"""Placement in the shipped maps: where an object ends up versus where it was drawn.

Three places read the object's rectangle differently from how it was authored,
and all three fail silently -- the map loads, the game runs, and the thing is
simply somewhere else. A 68x186 flag used to be reachable from a 64x64 box two
body heights above its head; an orbiting hazard was placed at its marker's
top-left corner instead of its centre; and a map tiled at anything other than
the world's tile size produced a level whose camera, index and sprites
disagreed about where everything was.
"""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.core.level.level_data import DATA_LAYER_NAME, LevelDataError
from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.core.level.world_builder import WorldBuilder
from src.core.sprite_groups import SpriteGroups
from src.core.sprites import LevelExit


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


@pytest.fixture(scope="module")
def level_data():
    return LevelManager(LEVEL_PATHS).get(0)


def test_the_exit_trigger_follows_the_flag_that_was_drawn(level_data) -> None:
    groups = SpriteGroups()
    WorldBuilder(level_data=level_data).build(groups, object())
    flag = next(
        obj
        for layer in level_data.object_layers.values()
        for obj in layer.objects
        if obj.name == "flag"
    )
    exit_sprite = next(iter(groups.exit_sprites))

    assert float(exit_sprite.rect.width) == pytest.approx(flag.width)
    assert float(exit_sprite.rect.height) == pytest.approx(flag.height)
    assert float(exit_sprite.rect.topleft[0]) == pytest.approx(flag.x)
    assert float(exit_sprite.rect.topleft[1]) == pytest.approx(flag.y)


def test_a_point_sized_object_still_gets_a_trigger() -> None:
    """An author who places a flag as a point, not a rectangle, is not punished."""
    sprite = LevelExit((10.0, 20.0), None)
    assert (sprite.rect.width, sprite.rect.height) == (64, 64)


def test_an_empty_object_does_not_produce_a_zero_sized_trigger() -> None:
    sprite = LevelExit((10.0, 20.0), None, (0.0, 0.0))
    assert sprite.rect.width > 0
    assert sprite.rect.height > 0


def test_a_map_tiled_at_another_size_is_refused() -> None:
    from src.core.level.level_data import LevelData

    stub = SimpleNamespace(
        width=4,
        height=4,
        tilewidth=32,
        layers=[],
    )
    with pytest.raises(LevelDataError) as raised:
        LevelData.from_tmx(stub)
    assert "32px" in str(raised.value)

    stub.tilewidth = 64
    assert LevelData.from_tmx(stub).tile_size == 64


def test_the_data_layer_name_is_one_constant() -> None:
    """The build loop, the parser and the tests must not spell it three ways."""
    assert DATA_LAYER_NAME == "Data"
