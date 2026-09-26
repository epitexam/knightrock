"""Every drawing surface must be the render target, and must stay it.

The question this answers is "was the whole drawing path adapted", which is not
something a test suite proves by being green. It is a question about a *chain*:
the game hands a surface to a level, the level hands it to a renderer, the
renderer to a UI manager, the manager to a panel renderer and a HUD, and each of
them either stores it or derives it. One link that remembers the old one, and
the frame is painted in two places at once -- which shows up as nothing at all
until the two sizes differ, i.e. exactly when the player drags the window.
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
from src.ui.scale import PANEL_MAX_SCALE  # noqa: E402

#: Densities worth walking the chain through: whole numbers, the awkward
#: fractions a real display produces, and one below one.
DENSITIES = (1.0, 1.25, 2176 / 1152, 2.0, 0.5)


def _renderer(density: float) -> Renderer:
    target = Viewport(DEFAULT_FRAMING, _target_size(density)).surface
    return Renderer(target, Camera.for_target(target))


def _target_size(density: float) -> tuple[int, int]:
    return (
        round(DEFAULT_FRAMING.width * density),
        round(DEFAULT_FRAMING.height * density),
    )


def _chain(renderer: Renderer) -> list[pygame.Surface]:
    """Every surface the frame is drawn through, in order."""
    return [
        renderer.surface,
        renderer.ui_manager.renderer.surface,
        renderer.ui_manager.world_ui.surface,
        renderer.ui_manager.hud.renderer.surface,
    ]


@pytest.mark.parametrize("density", DENSITIES)
def test_the_whole_chain_starts_on_the_render_target(density: float) -> None:
    target = Viewport(DEFAULT_FRAMING, _target_size(density)).surface
    renderer = Renderer(target, Camera(DEFAULT_FRAMING))

    assert all(surface is target for surface in _chain(renderer))


@pytest.mark.parametrize("before,after", [(1.0, 2.0), (2.0, 1.25), (2.0, 0.5), (1.25, 1.8889)])
def test_the_whole_chain_follows_a_window_change(before: float, after: float) -> None:
    """The only path that replaces the target, so it is the one that can break.

    A window drag used to be the thing that could not happen, because the target
    was a constant and the picture was scaled onto the window afterwards. Now it
    is the everyday case, and it is the same code path as a display change.
    """
    renderer = _renderer(before)

    renderer.set_surface(Viewport(DEFAULT_FRAMING, _target_size(after)).surface)

    assert all(surface is renderer.surface for surface in _chain(renderer))
    assert renderer.surface.get_size() == _target_size(after)


def test_nothing_draws_into_the_window() -> None:
    """The window surface is a presentation detail and nobody may draw on it.

    The old arrangement made it the one surface everything drew into, which is
    the whole reason a video setting could reach the picture.
    """
    renderer = _renderer(1.0)
    window = pygame.display.get_surface()

    assert window is not None
    assert renderer.surface is not window
    for surface in _chain(renderer):
        assert surface is not window


def test_the_camera_does_not_know_the_target_size() -> None:
    """The invariant the whole chain exists to protect, at the end of it."""
    camera = _renderer(1.0).camera
    before = (camera.viewport_width, camera.viewport_height)

    _renderer(1.0).set_surface(Viewport(DEFAULT_FRAMING, _target_size(3.0)).surface)

    assert (camera.viewport_width, camera.viewport_height) == before
    assert before == DEFAULT_FRAMING.size


def test_the_pixel_density_is_derived_not_stored() -> None:
    """It comes from the camera, which reads it off the target.

    A second derivation in the renderer would be one too many: the camera uses
    the number for the rectangles, so a disagreement scales the images and not
    the rects, and the frame shows a world at the wrong size with no error.
    """
    for density in DENSITIES:
        renderer = _renderer(density)
        assert renderer._density == pytest.approx(density, abs=1e-3)
        assert renderer._density == renderer.camera.density

        # A surface of a different density moves it, because the camera hears
        # about the new target.
        renderer.set_surface(Viewport(DEFAULT_FRAMING, _target_size(1.0)).surface)
        assert renderer._density == 1.0
        assert renderer.camera.density == 1.0


def test_the_debug_overlay_and_the_renderer_agree_on_the_density() -> None:
    """Both read the same density, and both get it at construction.

    The overlay used to be handed the density only when the target changed, and
    a renderer built on a scaled target started with a 24px panel font on a 4K
    screen: one frame of, and then forever of, text half the size it should be.
    The constructor is the only place that can be right, so the test drives it.
    """
    for density in DENSITIES:
        renderer = _renderer(density)
        panel_renderer = renderer.ui_manager.renderer
        # The world scale never drops below one: below it, a world overlay
        # thins towards nothing instead of following the world.
        assert panel_renderer.world_scale == pytest.approx(max(1.0, density))
        # The screen scale is capped, so a 4K window gets readable panels
        # rather than panels that eat the display.
        assert panel_renderer.screen_scale == pytest.approx(min(max(1.0, density), PANEL_MAX_SCALE))
        assert panel_renderer.debug_font.get_height() > 0


@pytest.mark.parametrize("density", DENSITIES)
def test_the_frame_is_geometry_coherent_at_every_density(density: float) -> None:
    """Surface identity was not enough, and that is how the scale bug survived.

    A chain of surfaces can all be the right object and still draw a broken
    frame, if the camera's scale and the renderer's disagree: the rectangles
    come from the camera, the images from the renderer, and ``pygame.blit``
    resamples a source to fit a destination that does not match without saying
    anything. So the check has to be that a sprite's scaled image and its blit
    rect are the same size, at every scale.
    """
    from src.core.sprite_groups import SpriteGroups

    renderer = _renderer(density)
    groups = SpriteGroups()
    sprite = pygame.sprite.Sprite()
    sprite.image = pygame.Surface((64, 64), pygame.SRCALPHA)
    sprite.image.fill((0, 255, 0, 255))
    sprite.rect = pygame.FRect(0.0, 0.0, 64.0, 64.0)
    groups.all_sprites.add(sprite)

    image, rect = renderer._collect_visible_blits(groups)[0]

    assert renderer.camera.density == pytest.approx(density, abs=1e-3)
    assert image.get_size() == renderer.camera.scaled_size((64, 64))
    assert rect.size == image.get_size(), (
        "a blit whose source and destination differ is silently resampled"
    )


def test_a_frame_reaches_the_target_and_nothing_else() -> None:
    """One draw, and it lands on the target -- the whole point of the refactor."""
    from src.core.sprite_groups import SpriteGroups

    renderer = _renderer(1.0)
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
