"""Dirty-rect rendering tests (Phase 2 #2)."""

import os

import pygame
import pytest

from src.core.rendering.camera import Camera
from src.core.rendering.renderer import (
    DIRTY_RECT_COUNT_LIMIT,
    HEALTH_BAR_ANCHOR_GAP,
    HEALTH_BAR_HEIGHT,
    Renderer,
)
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


class BarredSprite(StaticSprite):
    """An entity that ``draw_health_bars`` will put a bar over."""

    faction = "enemy"
    is_dead = False
    max_health = 100

    def __init__(self, topleft: tuple[float, float], size: int = 24):
        super().__init__(topleft, (size, size))
        self.health = 100


def make_renderer() -> tuple[Renderer, SpriteGroups, pygame.Surface]:
    surface = pygame.Surface((64, 64))
    # zoom=1.0: these tests assert world-space screen rects, not the zoom.
    camera = Camera(64, 64, zoom=1.0)
    camera.set_world_size(128, 128)
    return Renderer(surface, camera), SpriteGroups(), surface


def test_draw_without_sprites_returns_no_dirty_rects():
    renderer, groups, _ = make_renderer()

    assert renderer.draw(groups) == []


def test_only_a_barred_sprite_gets_bar_headroom():
    """A static tile is not barred, so it must not pay the clearance.

    Headroom exists to cover the HP bar. Widening every terrain tile by 30px
    per side would be pure overdraw on ~900 sprites a level.
    """
    renderer, groups, _ = make_renderer()
    groups.all_sprites.add(StaticSprite((10, 10)))

    dirty = renderer.draw(groups)

    assert len(dirty) == 1
    assert dirty[0].collidepoint(10, 10)
    assert dirty[0].top == 10  # no clearance on a tile


def test_a_barred_entity_gets_clearance_on_every_side():
    """The bar is 30px wide and flips below near the top: clear all round.

    With headroom only on the top edge, the bar painted outside the region
    the next frame erases, leaving a 6px stripe behind every moving enemy.
    """
    renderer, groups, _ = make_renderer()
    groups.all_sprites.add(BarredSprite((20, 20)))

    dirty = renderer.draw(groups)

    assert len(dirty) == 1
    rect = dirty[0]
    assert rect.collidepoint(20, 20)  # the sprite
    # The bar spans 30px centred on a narrow sprite, so the rect must be wider
    # than the sprite on both sides and taller both ways (for the flip below).
    assert rect.width >= 30
    assert rect.top <= 20 - (HEALTH_BAR_ANCHOR_GAP + HEALTH_BAR_HEIGHT)
    assert rect.bottom > 20 + HEALTH_BAR_ANCHOR_GAP + HEALTH_BAR_HEIGHT
    assert rect.left < 20
    assert rect.right > 20


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


def test_a_viewport_filling_union_falls_back_to_a_full_refresh() -> None:
    """The partial update must give up when its union covers the screen.

    Once the union approaches the viewport the frame is filled, culled and
    blitted almost as if there were no dirty tracking, and it still pays a
    per-rect present cost. Measured, that hybrid was slower than the plain
    full refresh it was meant to avoid.
    """
    surface = pygame.Surface((64, 64))
    camera = Camera(64, 64, zoom=1.0)
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    groups.all_sprites.add(StaticSprite((0, 0), size=(64, 64)))

    assert renderer.draw(groups) is None


def test_a_full_refresh_repaints_everything() -> None:
    """The fallback path must still draw the world, not just clear it."""
    surface = pygame.Surface((64, 64))
    camera = Camera(64, 64, zoom=1.0)
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    groups.all_sprites.add(StaticSprite((0, 0), size=(64, 64)))

    renderer.draw(groups)

    assert surface.get_at((32, 32))[:3] == (255, 0, 0)


def test_a_small_dirty_region_is_kept() -> None:
    """The guard must not fire on a frame that really is a partial update."""
    surface = pygame.Surface((640, 640))
    camera = Camera(640, 640, zoom=1.0)
    camera.set_world_size(640, 640)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    groups.all_sprites.add(StaticSprite((10, 10), size=(8, 8)))

    dirty = renderer.draw(groups)

    assert dirty is not None
    assert len(dirty) == 1


def test_too_many_rects_falls_back_even_when_the_area_is_small() -> None:
    """Many scattered rects are also not worth presenting one by one."""
    surface = pygame.Surface((640, 640))
    camera = Camera(640, 640, zoom=1.0)
    camera.set_world_size(640, 640)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    for index in range(DIRTY_RECT_COUNT_LIMIT + 2):
        groups.all_sprites.add(StaticSprite((index * 9, 0), size=(4, 4)))

    assert renderer.draw(groups) is None


def test_debug_mode_returns_none_for_full_refresh():
    renderer, groups, _ = make_renderer()
    sprite = StaticSprite((10, 10))
    groups.all_sprites.add(sprite)

    assert renderer.draw(groups, debug_enabled=True) is None
