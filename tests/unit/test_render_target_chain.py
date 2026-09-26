"""Every drawing surface must be the render target, and must stay it.

The question this answers is "was the whole drawing path adapted", which is not
something a test suite proves by being green. It is a question about a *chain*:
the game hands a surface to a level, the level hands it to a renderer, the
renderer to a UI manager, the manager to a panel renderer and a HUD, and each of
them either stores it or derives it. One link that remembers the old one, and
the frame is painted in two places at once -- which shows up as nothing at all
until the two sizes differ, i.e. exactly when the player changes the render
scale.
"""

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((320, 240))

from src.core.display.framing import DEFAULT_FRAMING  # noqa: E402
from src.core.display.viewport import Viewport  # noqa: E402
from src.core.rendering.camera import Camera  # noqa: E402
from src.core.rendering.renderer import Renderer  # noqa: E402


def _renderer(scale: int) -> Renderer:
    return Renderer(Viewport(DEFAULT_FRAMING, scale).surface, Camera(DEFAULT_FRAMING))


def _chain(renderer: Renderer) -> list[pygame.Surface]:
    """Every surface the frame is drawn through, in order."""
    return [
        renderer.surface,
        renderer.ui_manager.renderer.surface,
        renderer.ui_manager.world_ui.surface,
        renderer.ui_manager.hud.renderer.surface,
    ]


@pytest.mark.parametrize("scale", [1, 2, 3])
def test_the_whole_chain_starts_on_the_render_target(scale: int) -> None:
    target = Viewport(DEFAULT_FRAMING, scale).surface
    renderer = Renderer(target, Camera(DEFAULT_FRAMING))

    assert all(surface is target for surface in _chain(renderer))


@pytest.mark.parametrize("from_scale,to_scale", [(1, 2), (2, 3), (2, 1), (3, 1)])
def test_the_whole_chain_follows_a_render_scale_change(from_scale, to_scale) -> None:
    """The only path that replaces the target, so it is the one that can break."""
    renderer = _renderer(from_scale)

    renderer.set_surface(Viewport(DEFAULT_FRAMING, to_scale).surface)

    assert all(surface is renderer.surface for surface in _chain(renderer))
    assert renderer.surface.get_size() == DEFAULT_FRAMING.viewport_size(to_scale)


def test_nothing_draws_into_the_window() -> None:
    """The window surface is a presentation detail and nobody may draw on it.

    The old arrangement made it the one surface everything drew into, which is
    the whole reason a video setting could reach the picture.
    """
    renderer = _renderer(1)
    window = pygame.display.get_surface()

    assert window is not None
    assert renderer.surface is not window
    for surface in _chain(renderer):
        assert surface is not window


def test_the_camera_does_not_know_the_target_size() -> None:
    """The invariant the whole chain exists to protect, at the end of it."""
    camera = _renderer(1).camera
    before = (camera.viewport_width, camera.viewport_height)

    _renderer(1).set_surface(Viewport(DEFAULT_FRAMING, 3).surface)

    assert (camera.viewport_width, camera.viewport_height) == before
    assert before == DEFAULT_FRAMING.size


def test_the_render_scale_is_derived_not_stored() -> None:
    """Read off the two sizes, so a scale that disagrees with the surface is
    not expressible."""
    for scale in (1, 2, 3):
        renderer = _renderer(scale)
        assert renderer._render_scale == float(scale)

        # A surface of a different scale moves the derivation with it.
        renderer.set_surface(Viewport(DEFAULT_FRAMING, 1).surface)
        assert renderer._render_scale == 1.0


def test_the_debug_overlay_and_the_renderer_agree_on_the_scale() -> None:
    """Two independent derivations of the same number; they must not drift."""
    for scale in (1, 2, 3):
        renderer = _renderer(scale)
        overlay = renderer.ui_manager.world_ui
        assert overlay._target_scale(renderer.camera) == renderer._render_scale


def test_a_frame_reaches_the_target_and_nothing_else() -> None:
    """One draw, and it lands on the target -- the whole point of the refactor."""
    from src.core.sprite_groups import SpriteGroups

    renderer = _renderer(1)
    target = renderer.surface
    target.fill((0, 0, 0))
    groups = SpriteGroups()

    sprite = pygame.sprite.Sprite()
    sprite.image = pygame.Surface((8, 8), pygame.SRCALPHA)
    sprite.image.fill((200, 40, 40, 255))
    sprite.rect = pygame.FRect(0.0, 0.0, 8, 8)
    groups.all_sprites.add(sprite)

    renderer.draw(groups, alpha=1.0)

    assert target.get_at((4, 4))[:3] == (200, 40, 40)
    window = pygame.display.get_surface()
    assert window is not None
    assert window.get_at((4, 4))[:3] != (200, 40, 40), "nothing may reach the window"
