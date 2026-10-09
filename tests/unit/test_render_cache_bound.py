"""The render caches must not grow with everything the game has ever drawn.

``_scaled_image`` and ``_silhouette`` memoise one entry per *source surface*,
and the key is ``id`` -- so a freed surface's id is recycled and the entry
stays behind, holding the surface alive. The debug spawn bench makes a new
Surface for every enemy it spawns and destroys, on a half-second cooldown: the
caches were measured growing by about 29 Ko per spawned enemy and never giving
it back, for the rest of the session.

Two failure modes are pinned here, because they pull in opposite directions:
a bound that is too small rebuilds the cache every frame, and the shear cache's
own first bound did exactly that at 95us a frame; a bound that is too generous
is the leak it was meant to stop.
"""

import os

import pygame
import pytest

from src.core.colors import Colors
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import (
    FLASH_CACHE_MAX,
    SCALE_CACHE_MAX,
    Renderer,
)


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


def _renderer() -> Renderer:
    return Renderer(pygame.Surface((1280, 720)), Camera.for_target(pygame.Surface((1280, 720))))


def _surface(size=(36, 48)) -> pygame.Surface:
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill((10, 20, 30, 255))
    return surface


def test_churning_surfaces_does_not_grow_the_scale_cache() -> None:
    renderer = _renderer()
    for _ in range(4000):
        renderer._scaled_image(_surface())
    assert len(renderer._scaled_cache) <= SCALE_CACHE_MAX


def test_churning_surfaces_does_not_grow_the_flash_cache() -> None:
    renderer = _renderer()
    for _ in range(4000):
        renderer._silhouette(_surface(), Colors.red)
    assert len(renderer._flash_cache) <= FLASH_CACHE_MAX


def test_a_frame_s_worth_of_distinct_images_never_evicts() -> None:
    """The bound sits above the working set, not inside it.

    Measured on the shipped level: 38 distinct images through the scale cache
    in a frame. A bound at that number evicts every frame, which is the shear
    cache's 100%-rebuild mistake.
    """
    renderer = _renderer()
    for index in range(200):
        renderer._scaled_image(_surface((36 + index % 20, 48)))

    assert len(renderer._scaled_cache) == 200, (
        "a frame's worth of distinct images was evicted, so the cache rebuilds them every frame"
    )


def test_a_scale_entry_keeps_the_source_it_was_built_from() -> None:
    renderer = _renderer()
    source = _surface()
    renderer._scaled_image(source)
    assert any(held is source for held, _ in renderer._scaled_cache.values())


def test_a_flash_entry_keeps_the_source_it_was_built_from() -> None:
    renderer = _renderer()
    source = _surface()
    renderer._silhouette(source, Colors.red)
    assert any(held is source for held, _ in renderer._flash_cache.values())
