"""Regression guards for the frame presentation and asset-lifetime bugs.

Each test here corresponds to a defect that cost a frame or a memory leak in a
silently wrong way: a cache that grew without bound, HP bars painted outside
the presented area, and converted surfaces surviving the display teardown they
depend on. They count operations rather than timing, so they stay deterministic.
"""

import os
from dataclasses import replace

import pygame
import pytest

from src.core import fx
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.viewport import Viewport
from src.core.game import Game
from src.core.level.level import Level
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.sprite_groups import SpriteGroups
from tests.headless.conftest import make_programmatic_level_data, make_viewport


@pytest.fixture()
def game_runtime(tmp_path):
    """A runtime bound to a temporary settings file, without the main loop."""
    runtime = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    runtime.initialize_display()
    runtime.clock = pygame.time.Clock()
    return runtime


@pytest.fixture(scope="module", autouse=True)
def _renderer_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


class _Sprite(pygame.sprite.Sprite):
    """Minimal sprite: a fixed image, a world rect, and a camera-cullable size."""

    def __init__(self, topleft: tuple[float, float] = (8.0, 8.0), size: int = 40) -> None:
        super().__init__()
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        self.rect = pygame.FRect(topleft, (size, size))


class _RebuiltSprite(_Sprite):
    """An FX-like particle that rebuilds its image every tick, like fx.py does."""

    def rebuild(self) -> None:
        self.image = pygame.Surface((40, 40), pygame.SRCALPHA)


def make_renderer(scale: int = 1) -> tuple[Renderer, SpriteGroups]:
    """A renderer on a target built the way the game builds one.

    The framing is the game's, not a test's own: a test that picks a framing
    and a surface separately can produce a pair the game would refuse, and then
    it tests a configuration that cannot occur.
    """
    surface = Viewport(DEFAULT_FRAMING, scale).surface
    camera = Camera.for_target(surface)
    camera.set_world_size(640, 480)
    return Renderer(surface, camera), SpriteGroups()


def test_fx_sprites_do_not_grow_the_scale_cache() -> None:
    """The scale cache must stay bounded while FX particles churn.

    FX rebuild their image every tick, so caching them by ``id(image)``
    retained one surface per particle per tick for the whole session, with no
    eviction: a minute of combat was measured retaining tens of megabytes.
    """
    renderer, groups = make_renderer(2)
    groups.all_sprites.add(_Sprite())
    for _ in range(200):
        particle = _RebuiltSprite()
        particle.rebuild()
        groups.fx_sprites.add(particle)
        renderer._collect_visible_blits(groups)
        groups.fx_sprites.empty()

    assert len(renderer._scaled_cache) == 1


def test_static_sprites_are_still_cached_across_frames() -> None:
    """The fix must not disable caching for the planes that benefit from it."""
    renderer, groups = make_renderer(2)
    groups.all_sprites.add(_Sprite())

    renderer._collect_visible_blits(groups)
    renderer._collect_visible_blits(groups)

    assert len(renderer._scaled_cache) == 1


def test_fx_sprites_are_still_scaled_to_the_render_scale() -> None:
    """Not caching FX must not skip the render scale."""
    renderer, groups = make_renderer(2)
    groups.fx_sprites.add(_RebuiltSprite())

    blits = renderer._collect_visible_blits(groups)

    assert [surface.get_size() for surface, _ in blits] == [(80, 80)]
    # And the rect agrees, or pygame silently resamples the source to fit it.
    assert [rect.size for _, rect in blits] == [(80, 80)]


def test_health_bars_report_the_rects_they_paint() -> None:
    """A bar drawn outside the dirty set never reaches the screen.

    The bar flips below its entity near the top of the screen, and its 30px
    minimum width is wider than a narrow sprite, so it is not always inside
    the sprite's own rect.
    """
    renderer, groups = make_renderer(1)
    entity = _Sprite((100.0, 100.0), size=16)
    entity.max_health = 100
    entity.health = 40

    rects = renderer.draw_health_bars([entity])

    assert rects, "a visible damaged entity must report the rect it painted"
    assert all(rect.width > 0 and rect.height > 0 for rect in rects)


def test_health_bars_report_nothing_without_health() -> None:
    renderer, _ = make_renderer(1)
    entity = _Sprite()
    entity.max_health = 0
    entity.health = 0

    assert renderer.draw_health_bars([entity]) == []


def test_a_resolution_change_drops_the_converted_art(game_runtime) -> None:
    """``set_mode`` invalidates converted surfaces, so both caches must go.

    ``AssetLibrary`` has no display to compare against and cannot notice on
    its own, which left stale surfaces being blitted through a software alpha
    path and a full re-decode of the art on the next frame that touched a new
    animation.
    """
    from src.core.asset_library import shared_library

    game = game_runtime
    game.initialize_display()
    library = shared_library()
    library._cache["sentinel"] = pygame.Surface((1, 1), pygame.SRCALPHA)
    library._frame_cache["sentinel"] = [pygame.Surface((1, 1), pygame.SRCALPHA)]
    fx._frames_cache = [pygame.Surface((1, 1), pygame.SRCALPHA)]
    fx._frames_miss = True

    game.apply_settings(replace(game.settings, width=800, height=600))

    assert library._cache == {}
    assert library._frame_cache == {}
    assert fx._frames_cache is None
    assert fx._frames_miss is False


def test_a_ui_scale_change_keeps_the_converted_art(game_runtime) -> None:
    """The caches only go when the display format actually changes."""
    from src.core.asset_library import shared_library

    game = game_runtime
    game.initialize_display()
    library = shared_library()
    library._cache["sentinel"] = pygame.Surface((1, 1), pygame.SRCALPHA)

    game.apply_settings(replace(game.settings, ui_scale=1.2))

    assert "sentinel" in library._cache


def test_fx_frame_cache_forgets_a_missing_asset_tree() -> None:
    """A cleared miss must be retried, or the fallback art never comes back."""
    fx._frames_cache = None
    fx._frames_miss = True

    fx.clear_frame_cache()

    assert fx._frames_cache is None
    assert fx._frames_miss is False


def test_level_draw_paints_the_health_bars_over_the_world(mock_input_manager) -> None:
    """The bars are on the target when ``Level.draw`` returns.

    They used to have to be *declared* so the next frame's partial present
    would reach them, and this is the test that contract died with: there is no
    declared set and no partial present, so the only thing left to check is
    that a bar actually reaches the pixels.
    """
    level = Level(
        make_viewport().surface,
        make_programmatic_level_data(),
        mock_input_manager,
    )
    level.update(1 / 60)
    enemy = _Sprite((200.0, 200.0), size=40)
    enemy.faction = "enemy"
    enemy.max_health = 80
    enemy.health = 30
    enemy.is_dead = False
    level.groups.entity_sprites.add(enemy)

    assert level.draw(60.0, game=None, frame_time=16.0) is None

    rects = level.renderer.draw_health_bars(level.groups.entity_sprites)
    assert rects, "a damaged enemy must get a bar"
    assert not hasattr(level.renderer, "add_overlay_rects")
