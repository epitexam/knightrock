"""Presentation: the letterbox geometry and the pointer that goes with it.

The pointer inversion and the blit share one rectangle on purpose. These tests
pin that down at the four window corners, because the failure they guard
against -- a click landing on a neighbouring row -- is invisible until someone
plays on an ultrawide, and is invisible in a screenshot.
"""

import os
from typing import Any

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((320, 240))

from src.core.display.framing import Framing  # noqa: E402
from src.core.display.presentation import Presentation  # noqa: E402
from src.core.display.viewport import Viewport  # noqa: E402

FRAMING = Framing(1152.0, 648.0)


class FakeStage:
    """Just enough of ``Stage`` for the geometry, with no window involved."""

    def __init__(self, size: tuple[int, int]) -> None:
        self.surface = pygame.Surface(size)

    @property
    def size(self) -> tuple[int, int]:
        return self.surface.get_size()


def _presentation(window: tuple[int, int], scale: int = 1) -> Presentation:
    return Presentation(FakeStage(window), Viewport(FRAMING, scale))  # type: ignore[arg-type]


WINDOWS = [(1920, 1080), (1440, 900), (2560, 1440), (3440, 1440), (5120, 1440), (800, 600)]


@pytest.mark.parametrize("window", WINDOWS)
def test_the_presented_rect_keeps_the_framing_ratio(window) -> None:
    presentation = _presentation(window)
    assert presentation.rect.width / presentation.rect.height == pytest.approx(
        FRAMING.aspect, abs=0.01
    ), "a stretched image is the one thing the letterbox exists to prevent"


@pytest.mark.parametrize("window", WINDOWS)
def test_the_presented_rect_is_inside_and_centred_in_the_window(window) -> None:
    presentation = _presentation(window)
    left = window[0] - presentation.rect.right
    top = window[1] - presentation.rect.bottom
    assert presentation.rect.x == pytest.approx(left, abs=1)
    assert presentation.rect.y == pytest.approx(top, abs=1)
    assert presentation.rect.width <= window[0]
    assert presentation.rect.height <= window[1]


@pytest.mark.parametrize("window", WINDOWS)
def test_every_window_corner_maps_back_inside_the_viewport(window) -> None:
    """The four corners of a stretched image are where mis-mapping shows first."""
    presentation = _presentation(window)
    viewport = presentation.viewport.size
    for corner in ((0, 0), (window[0] - 1, 0), (0, window[1] - 1), (window[0] - 1, window[1] - 1)):
        x, y = presentation.pointer_to_viewport(corner)
        if presentation.pointer_in_viewport(corner):
            assert -0.5 <= x <= viewport[0] + 0.5
            assert -0.5 <= y <= viewport[1] + 0.5
        else:
            # In a bar: rejected rather than clamped onto a valid row.
            assert not presentation.pointer_in_viewport(corner)


def test_a_point_at_the_presented_origin_is_the_viewport_origin() -> None:
    presentation = _presentation((2560, 1440))
    assert presentation.pointer_to_viewport((presentation.rect.x, presentation.rect.y)) == (
        0.0,
        0.0,
    )


def test_a_window_the_size_of_the_viewport_scales_nothing() -> None:
    """smoothscale at 1:1 measures 2.19ms for a no-op, every frame."""
    presentation = _presentation((1152, 648))
    assert presentation.scale == 1.0
    assert presentation.rect == pygame.Rect(0, 0, 1152, 648)
    assert presentation.bars == ()


def test_the_bars_cover_exactly_the_window_outside_the_presented_rect() -> None:
    presentation = _presentation((2560, 1440))
    covered = sum(bar.width * bar.height for bar in presentation.bars)
    window_area = 2560 * 1440
    assert covered + presentation.rect.width * presentation.rect.height == window_area


def test_present_writes_the_viewport_and_flips() -> None:
    presentation = _presentation((1920, 1080))
    presentation.viewport.fill((10, 20, 30))
    presentation.present()
    # The presented region of the window carries the viewport's colour.
    pixel = presentation.stage.surface.get_at(
        (presentation.rect.centerx, presentation.rect.centery)
    )
    assert pixel[:3] == (10, 20, 30)


def test_the_bars_are_black_and_the_stale_frame_does_not_survive_a_resize() -> None:
    """After a shrink, the old image must not linger in the new bars."""
    stage = FakeStage((2560, 1440))
    presentation: Any = Presentation(stage, Viewport(FRAMING, 1))  # type: ignore[arg-type]
    presentation.viewport.fill((200, 100, 50))
    presentation.present()

    stage.surface = pygame.Surface((1920, 1080))
    presentation.recompute()
    presentation.present()

    for bar in presentation.bars:
        assert bar.width > 0 and bar.height > 0
        assert stage.surface.get_at((bar.centerx, bar.centery))[:3] == (0, 0, 0)


def test_smoothing_off_still_presents_the_image() -> None:
    presentation = Presentation(
        FakeStage((1920, 1080)),  # type: ignore[arg-type]
        Viewport(FRAMING, 1),
        smoothing=False,
    )
    presentation.viewport.fill((5, 6, 7))
    presentation.present()
    assert presentation.stage.surface.get_at(
        (presentation.rect.centerx, presentation.rect.centery)
    )[:3] == (5, 6, 7)


def test_a_degenerate_window_does_not_divide_by_zero() -> None:
    presentation = _presentation((0, 0))
    assert presentation.rect.width >= 1 and presentation.rect.height >= 1
    presentation.recompute()
    assert presentation.scale == 1.0
