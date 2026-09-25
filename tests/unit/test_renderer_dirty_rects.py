"""Dirty-rect rendering tests (Phase 2 #2)."""

import os

import pygame
import pytest

from src.core.rendering.camera import Camera
from src.core.rendering.renderer import HEALTH_BAR_CLEARANCE_PX, Renderer
from src.core.sprite_groups import SpriteGroups


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    """Initialize a dummy SDL display for the whole session."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


class StaticSprite(pygame.sprite.Sprite):
    """Minimal sprite with a fixed image and a movable rect."""

    def __init__(self, topleft: tuple[float, float], size: tuple[int, int] = (8, 8)):
        super().__init__()
        self.image = pygame.Surface(size)
        self.image.fill((255, 0, 0))
        self.rect = pygame.FRect(topleft, size)


def make_renderer() -> tuple[Renderer, SpriteGroups, pygame.Surface]:
    surface = pygame.Surface((64, 64))
    # zoom=1.0: these tests assert world-space screen rects, not the zoom.
    camera = Camera(64, 64, zoom=1.0)
    camera.set_world_size(128, 128)
    return Renderer(surface, camera), SpriteGroups(), surface


def test_draw_without_sprites_returns_no_dirty_rects():
    renderer, groups, _ = make_renderer()

    assert renderer.draw(groups) == []


def test_draw_returns_sprite_rect_with_health_bar_clearance():
    renderer, groups, _ = make_renderer()
    sprite = StaticSprite((10, 10))
    groups.all_sprites.add(sprite)

    dirty = renderer.draw(groups)

    assert len(dirty) == 1
    assert dirty[0].collidepoint(10, 10)
    assert dirty[0].top <= 10 - HEALTH_BAR_CLEARANCE_PX


def test_draw_keeps_previous_frame_region_to_avoid_ghosts():
    renderer, groups, _ = make_renderer()
    sprite = StaticSprite((10, 10))
    groups.all_sprites.add(sprite)
    renderer.draw(groups)

    # The camera follows the player: simulate a view offset.
    sprite.rect.topleft = (40, 40)
    dirty = renderer.draw(groups)

    positions = [tuple(r.topleft) for r in dirty]
    assert any(10 in (x, x + 8) for x, _ in positions)  # old position covered
    assert any(40 in (x, x + 8) for x, _ in positions)  # new position covered


def test_background_is_repainted_only_over_dirty_area():
    renderer, groups, surface = make_renderer()
    sprite = StaticSprite((10, 10))
    groups.all_sprites.add(sprite)
    renderer.draw(groups)

    # Never-dirtied opposite corner: it must keep the background color
    # present BEFORE the second draw (no full-screen fill).
    surface.set_at((63, 63), (1, 2, 3))
    sprite.rect.topleft = (40, 40)
    renderer.draw(groups)

    assert surface.get_at((63, 63)) == (1, 2, 3)


def test_debug_mode_returns_none_for_full_refresh():
    renderer, groups, _ = make_renderer()
    sprite = StaticSprite((10, 10))
    groups.all_sprites.add(sprite)

    assert renderer.draw(groups, debug_enabled=True) is None
