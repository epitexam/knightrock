"""A new render target brings the level's tiles to the display's format."""

from __future__ import annotations

import pygame

from src.simulation.sprites import Sprite
from tests.headless.test_combat_dynamism import _arena


def test_a_new_render_target_reconverts_the_tile_planes() -> None:
    level, _pad, _player = _arena()
    tile = Sprite((0.0, 0.0), surf=pygame.Surface((64, 64), depth=16))
    level.groups.static_sprites.add(tile)
    display = pygame.display.get_surface()
    assert display is not None

    level.reconvert_tiles()

    assert tile.image.get_bitsize() == display.get_bitsize()
