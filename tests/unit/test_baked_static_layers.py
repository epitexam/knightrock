"""The opt-in pre-painted alternative to the chunked tile planes.

The producer is off in the shipped build: measured here, copying a whole
viewport out of a level-sized surface costs more than blitting the ~115 tiles
the chunk index leaves in view. These tests keep the alternative honest for
anyone who turns it on -- one blit, the same picture, and a real fallback when
the surface would be too large.
"""

from __future__ import annotations

import os

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((1152, 648))

from src.core.display.framing import DEFAULT_FRAMING  # noqa: E402
from src.core.display.letterbox import picture  # noqa: E402
from src.core.display.viewport import Viewport  # noqa: E402
from src.core.input.input_manager import InputManager  # noqa: E402
from src.core.level.level import Level  # noqa: E402
from src.core.level.level_manager import LEVEL_PATHS, LevelManager  # noqa: E402
from src.core.rendering.static_layer import bake_static_layer  # noqa: E402


def _level(window: tuple[int, int] = (1152, 648)) -> Level:
    size = picture(window, DEFAULT_FRAMING).dest.size
    return Level(
        Viewport(DEFAULT_FRAMING, size).surface,
        LevelManager(LEVEL_PATHS).get(0),
        InputManager(),
    )


def test_the_plane_is_one_viewport_sized_blit() -> None:
    level = _level()
    level.install_static_planes(bake=True)
    assert level.renderer._baked_static is not None
    assert level.renderer._static_index is None

    level.camera.offset.update(300.0, 200.0)
    level.camera.begin_frame(1.0)
    blits = level.renderer._collect_visible_blits(level.groups)
    image, rect = blits[0]
    assert image.get_size() == rect.size
    assert rect.size == picture((1152, 648), DEFAULT_FRAMING).dest.size
    assert len(blits) < 40, "the tiles were still blitted one by one"


def test_the_baked_frame_matches_the_chunked_frame() -> None:
    level = _level()
    assert level.renderer._baked_static is None, "the producer must be opt-in"

    # Integer offsets: the baked slice is the exact inverse of the camera for
    # every tile, including the handful of decor sprites with fractional rects.
    for offset in ((0.0, 0.0), (300.0, 200.0), (700.0, 400.0)):
        level.camera.offset.update(*offset)
        level.camera.begin_frame(1.0)
        level.camera.begin_frame(1.0)
        level.renderer.draw(level.groups, alpha=1.0)
        chunked = pygame.image.tobytes(level.renderer.surface, "RGB")

        level.install_static_planes(bake=True)
        level.camera.begin_frame(1.0)
        level.camera.begin_frame(1.0)
        level.renderer.draw(level.groups, alpha=1.0)
        baked = pygame.image.tobytes(level.renderer.surface, "RGB")
        assert baked == chunked, f"the plane changed the picture at {offset}"

        level.install_static_planes(bake=False)
        level.camera.begin_frame(1.0)
        level.camera.begin_frame(1.0)


def test_a_fractional_offset_can_move_fractional_decor_by_one_pixel() -> None:
    """The one pixel the translation cannot reproduce, measured and bounded.

    A baked plane has a single origin; the camera otherwise rounds each sprite
    separately. When a sprite's own fraction and the camera's fraction add past
    a whole pixel, the two roundings differ by one. It only affects decor with
    fractional rects at interpolated camera positions, and this test keeps the
    cost honest instead of pretending the two paths are byte-identical.
    """
    level = _level()
    level.camera.offset.update(700.5, 400.25)
    level.camera.begin_frame(1.0)
    level.camera.begin_frame(1.0)
    level.renderer.draw(level.groups, alpha=1.0)
    chunked = pygame.image.tobytes(level.renderer.surface, "RGB")

    level.install_static_planes(bake=True)
    level.camera.begin_frame(1.0)
    level.camera.begin_frame(1.0)
    level.renderer.draw(level.groups, alpha=1.0)
    baked = pygame.image.tobytes(level.renderer.surface, "RGB")
    differing = sum(left != right for left, right in zip(chunked, baked, strict=True))
    assert differing < 3 * 1000, f"{differing} colour bytes differ"


def test_a_plane_too_large_for_the_ceiling_is_refused() -> None:
    assert (
        bake_static_layer(
            (),
            size=(20000, 20000),
            density=1.0,
            background=(0, 0, 0),
            scale=lambda image: image,
            enabled=True,
        )
        is None
    )
    assert (
        bake_static_layer(
            (),
            size=(100, 100),
            density=1.0,
            background=(0, 0, 0),
            scale=lambda image: image,
        )
        is None
    ), "the producer must not be active in the shipped build"


def test_invalidating_the_planes_drops_them_until_rebuilt() -> None:
    level = _level()
    level.install_static_planes(bake=True)
    assert level.renderer._baked_static is not None

    level.invalidate_baked_layers()
    assert level.renderer._baked_static is None
    level.rebuild_baked_layers()
    assert level.renderer._baked_static is None, "rebuild must respect the opt-in"
    level.install_static_planes(bake=True)
    assert level.renderer._baked_static is not None
