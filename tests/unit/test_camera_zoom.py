"""Gameplay camera zoom: framing, culling and scaled presentation."""

import os

import pygame
import pytest

from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.settings import GameplayCamera
from src.core.sprite_groups import SpriteGroups


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1440, 900))


class StaticSprite(pygame.sprite.Sprite):
    def __init__(self, topleft, size=(16, 16), color=(255, 0, 0)):
        super().__init__()
        self.image = pygame.Surface(size)
        self.image.fill(color)
        self.rect = pygame.FRect(topleft, size)


def _settled(camera: Camera, target: pygame.FRect) -> None:
    """Run the follow long enough to converge on the target."""
    for _ in range(240):
        camera.follow(target, 1 / 60)


def test_gameplay_zoom_is_configured_above_one() -> None:
    """The shipped default tightens the framing on the player."""
    assert GameplayCamera.ZOOM > 1.0
    assert Camera(1440, 900).zoom == GameplayCamera.ZOOM


def test_zoom_shrinks_the_visible_world_area() -> None:
    """A higher zoom shows LESS world, which is the whole point."""
    camera = Camera(1440, 900, zoom=GameplayCamera.ZOOM)

    assert camera.viewport_width < 1440
    assert camera.viewport_height < 900
    assert camera.viewport_width == pytest.approx(1440 / GameplayCamera.ZOOM)
    assert camera.viewport_height == pytest.approx(900 / GameplayCamera.ZOOM)


def test_zoom_one_keeps_the_full_viewport_and_the_identity_mapping() -> None:
    """ZOOM = 1.0 restores the previous de-zoomed behaviour exactly."""
    camera = Camera(800, 600, zoom=1.0)
    box = pygame.FRect(100, 100, 40, 40)

    assert (camera.viewport_width, camera.viewport_height) == (800, 600)
    assert camera.apply(box) == box


def test_apply_scales_the_world_rect_onto_the_screen() -> None:
    camera = Camera(800, 600, zoom=2.0)

    screen = camera.apply(pygame.FRect(10, 20, 30, 40))

    assert screen.size == (60, 80)
    assert (screen.x, screen.y) == (20, 40)


def test_follow_centers_the_target_at_any_zoom() -> None:
    """The player stays centered; the zoom only changes how much is shown."""
    for zoom in (1.0, GameplayCamera.ZOOM, 2.0):
        camera = Camera(1440, 900, zoom=zoom)
        camera.set_world_size(20_000, 20_000)
        target = pygame.FRect(4000, 3000, 48, 96)
        _settled(camera, target)

        on_screen = camera.apply(target)
        assert on_screen.centerx == pytest.approx(1440 / 2, abs=1.0)
        assert on_screen.centery == pytest.approx(900 / 2, abs=1.0)


def test_culling_rejects_sprites_outside_the_zoomed_viewport() -> None:
    """A sprite visible at zoom 1 but off-screen at 1.15 must be culled."""
    visible_at_1 = Camera(1000, 1000, zoom=1.0)
    zoomed = Camera(1000, 1000, zoom=1.15)
    far_sprite = pygame.FRect(900, 0, 50, 50)

    assert visible_at_1.is_visible(far_sprite)
    assert not zoomed.is_visible(far_sprite)


def test_clamping_uses_the_zoomed_viewport_not_the_window() -> None:
    """At the level's right edge the camera may not scroll past the world."""
    camera = Camera(1000, 1000, zoom=2.0)
    camera.set_world_size(1500, 1500)
    _settled(camera, pygame.FRect(1450, 0, 10, 10))

    assert camera.offset.x == pytest.approx(1500 - camera.viewport_width)
    assert camera.offset.x >= 0.0


def test_set_viewport_size_keeps_the_zoom_and_reclamps() -> None:
    camera = Camera(800, 600, zoom=2.0)
    camera.set_world_size(2000, 2000)
    _settled(camera, pygame.FRect(1900, 1900, 10, 10))

    camera.set_viewport_size(1600, 1200)

    assert camera.zoom == 2.0
    assert (camera.viewport_width, camera.viewport_height) == (800, 600)
    assert camera.offset.x <= 2000 - camera.viewport_width


def test_set_zoom_reclamps_the_offset() -> None:
    """Zooming in narrows the scroll range: the offset stays inside it."""
    camera = Camera(1000, 1000, zoom=1.0)
    camera.set_world_size(1600, 1600)
    _settled(camera, pygame.FRect(1550, 1550, 10, 10))
    assert camera.offset.x == pytest.approx(600.0)  # pinned to the zoom-1 edge

    camera.set_zoom(2.0)

    # The maximum scroll shrank (1100 -> 550); the offset must respect it.
    assert camera.viewport_width == pytest.approx(500.0)
    assert camera.offset.x <= 1600 - camera.viewport_width
    _settled(camera, pygame.FRect(1550, 1550, 10, 10))
    assert camera.offset.x == pytest.approx(1600 - camera.viewport_width)


def test_a_non_positive_zoom_is_rejected() -> None:
    with pytest.raises(ValueError):
        Camera(800, 600, zoom=0.0)
    with pytest.raises(ValueError):
        Camera(800, 600, zoom=1.0).set_zoom(-1.0)


def test_shake_still_moves_the_screen_and_stays_deterministic() -> None:
    first, second = Camera(800, 600, zoom=1.15), Camera(800, 600, zoom=1.15)
    first.add_trauma(1.0)
    second.add_trauma(1.0)
    box = pygame.FRect(100, 100, 40, 40)

    assert first.apply(box) == second.apply(box)
    assert first.apply(box) != box


def test_renderer_draws_sprites_larger_than_their_world_size() -> None:
    """Zoom is visible: the blitted surface and its rect both grow."""
    surface = pygame.Surface((400, 400))
    camera = Camera(400, 400, zoom=2.0)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    sprite = StaticSprite((100, 100), size=(20, 20))
    groups.all_sprites.add(sprite)

    blits = renderer._collect_visible_blits(groups)

    assert len(blits) == 1
    image, screen_rect = blits[0]
    assert image.get_size() == (40, 40)
    assert screen_rect.size == (40, 40)
    # The simulation geometry is untouched by the render-only zoom.
    assert sprite.rect.size == (20, 20)


def test_scaled_surfaces_are_cached_and_reused() -> None:
    """Scaling once per (image, zoom) keeps the per-frame cost flat."""
    renderer = Renderer(pygame.Surface((400, 400)), Camera(400, 400, zoom=1.5))
    image = pygame.Surface((10, 10))

    first = renderer._scaled_image(image)
    second = renderer._scaled_image(image)

    assert first is second
    assert first.get_size() == (15, 15)


def test_zoom_one_returns_the_source_surface_untouched() -> None:
    renderer = Renderer(pygame.Surface((400, 400)), Camera(400, 400, zoom=1.0))
    image = pygame.Surface((10, 10))

    assert renderer._scaled_image(image) is image
    assert renderer._scaled_cache == {}


def test_transient_surfaces_are_scaled_without_filling_the_cache() -> None:
    """Afterimages/flashes build a new surface each frame: never cached."""
    renderer = Renderer(pygame.Surface((400, 400)), Camera(400, 400, zoom=1.5))

    scaled = renderer._scaled_image_once(pygame.Surface((10, 10)))

    assert scaled.get_size() == (15, 15)
    assert renderer._scaled_cache == {}


def test_changing_the_surface_drops_the_scaled_cache() -> None:
    renderer = Renderer(pygame.Surface((400, 400)), Camera(400, 400, zoom=1.5))
    renderer._scaled_image(pygame.Surface((10, 10)))
    assert renderer._scaled_cache

    renderer.set_display_surface(pygame.Surface((800, 600)))

    assert renderer._scaled_cache == {}


def test_a_resolution_change_keeps_the_zoom_on_the_new_viewport() -> None:
    """Switching resolution re-frames the world, it does not de-zoom it."""
    renderer = Renderer(pygame.Surface((1440, 900)), Camera(1440, 900, zoom=1.15))
    camera = renderer.camera

    renderer.set_display_surface(pygame.Surface((1280, 720)))

    assert camera.zoom == 1.15
    assert (camera.width, camera.height) == (1280, 720)
    assert camera.viewport_width == pytest.approx(1280 / 1.15)
