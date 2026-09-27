"""The dead type check is gone; the real gate is asserted instead."""

import os

import pygame
import pytest

from src.ui.world_ui import WorldUI


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


def _world_ui() -> WorldUI:
    from src.ui.panel_renderer import PanelRenderer

    return WorldUI(PanelRenderer(pygame.Surface((320, 240))))


def test_a_terrain_tile_is_a_sprite_subclass_not_a_bare_sprite() -> None:
    """The premise of the line that was removed.

    `type(tile) is pygame.sprite.Sprite` was false for every tile, because
    the tiles are `src.core.sprites.Sprite`, a subclass. The check was a
    `type()` call and a comparison per sprite per frame that could never
    match.
    """
    from src.core.sprites import Sprite

    tile = Sprite((0, 0))

    assert isinstance(tile, pygame.sprite.Sprite)
    assert type(tile) is not pygame.sprite.Sprite


def test_a_tile_has_no_hitbox_which_is_what_the_gate_actually_tests() -> None:
    from src.core.sprites import Sprite

    assert getattr(Sprite((0, 0)), "hitbox", None) is None


def test_the_overlay_source_no_longer_carries_the_exact_type_test() -> None:
    """Named so a revert is visible in a diff rather than in a frame time."""
    import inspect

    source = inspect.getsource(WorldUI.draw_debug_overlays)

    assert "type(sprite) is pygame.sprite.Sprite" not in source
    assert 'getattr(sprite, "hitbox", None) is None' in source
