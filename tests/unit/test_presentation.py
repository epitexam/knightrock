"""Presentation: the letterbox geometry, the 1:1 blit and the pointer.

The pointer inversion and the blit share one rectangle on purpose. These tests
pin that down at the four window corners, because the failure they guard
against -- a click landing on a neighbouring row -- is invisible until someone
plays on an ultrawide, and is invisible in a screenshot.

The frame is presented 1:1, so there is no ratio left anywhere in here: the
tests that used to divide by a ``fit`` now subtract, and one of them asserts
that the presented pixels are the drawn ones, which is the claim the whole
rework rests on.
"""

import os
from typing import Any

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()
pygame.display.set_mode((320, 240))

from src.application.settings_store import UI_SCALES  # noqa: E402
from src.core.display.framing import Framing  # noqa: E402
from src.core.display.letterbox import density_for, picture  # noqa: E402
from src.core.display.monitors import MIN_WINDOW  # noqa: E402
from src.core.display.presentation import Presentation  # noqa: E402
from src.ui.scale import MIN_UI_SCALE, checked_ui_scale  # noqa: E402

FRAMING = Framing(1152.0, 648.0)


class FakeStage:
    """Just enough of ``Stage`` for the geometry, with no window involved."""

    def __init__(self, size: tuple[int, int]) -> None:
        self.surface = pygame.Surface(size)

    @property
    def size(self) -> tuple[int, int]:
        return self.surface.get_size()


def _presentation(window: tuple[int, int], *, pixel_perfect: bool = False) -> Presentation:
    return Presentation(FakeStage(window).surface, FRAMING, pixel_perfect=pixel_perfect)


WINDOWS = [(1920, 1080), (1440, 900), (2560, 1440), (3440, 1440), (5120, 1440), (800, 600)]


def test_a_window_under_the_floor_keeps_the_last_target_it_could_draw() -> None:
    """A window too small to lay the interface out in is refused, not fitted.

    The interface has a scale floor of its own, and a window under the display's
    own floor puts the density below it: measured, a 240x180 window asks the
    interface for a scale of 0.21, which it refuses with an exception rather than
    a smaller font. So the window is not fitted at all -- the last drawable
    target stands, and the drag below the floor is clipped instead of fatal.

    The *first* fit is the exception that proves the rule: a runtime that opens
    on a window this small -- a headless caller, a platform that refused the
    minimum outright -- still gets a surface it can draw on, which is what a
    degenerate window has always meant here.
    """
    stage = FakeStage(MIN_WINDOW)
    presentation = Presentation(stage.surface, FRAMING)
    drawable = presentation.surface.get_size()

    # The presentation reads the surface it was handed, so that is what a resize
    # replaces -- a new object is what ``set_mode`` and SDL between them produce.
    presentation.stage = pygame.Surface((240, 180))  # type: ignore[assignment]
    assert presentation.recompute() is False, "a window this small was fitted anyway"
    assert presentation.surface.get_size() == drawable, "the target was replaced by one it refused"

    # And a window that grows again is fitted as if nothing had happened.
    presentation.stage = pygame.Surface((1920, 1080))  # type: ignore[assignment]
    assert presentation.recompute() is True
    assert presentation.surface.get_size() == (1920, 1080)

    # A presentation built *on* a degenerate window still has a surface.
    assert _presentation((0, 0)).surface.get_width() >= 1


def test_the_window_floor_is_a_size_the_interface_can_be_laid_out_in() -> None:
    """The display's floor and the interface's floor have to agree.

    They live in different layers -- ``core/display`` cannot import ``ui/scale``,
    and the presentation is the one place that refuses a window -- so the number
    is stated twice and pinned here instead. If either floor is raised without
    the other, a window that the display considers drawable asks the interface
    for a scale it refuses, and that refusal is an exception rather than a
    smaller font.
    """
    density = density_for(picture(MIN_WINDOW, FRAMING).target.size, FRAMING)

    for preference in UI_SCALES:
        assert checked_ui_scale(preference * density), (
            f"a {MIN_WINDOW} window at a preference of {preference} is not drawable"
        )
    # And the floor is not gratuitously high: the window just under it is refused
    # for a reason, and the window at it has room to spare.
    assert density > MIN_UI_SCALE / max(UI_SCALES)


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
    viewport = presentation.surface.get_size()
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


def test_a_window_the_size_of_the_framing_needs_no_bars() -> None:
    """The density of exactly 1, and nothing around the picture.

    The old version of this test was about a short-circuit: ``smoothscale`` at
    1:1 measures 2.19ms for a no-op, every frame, so the presentation skipped it.
    There is no transform left to skip.
    """
    presentation = _presentation((1152, 648))
    assert presentation.rect == pygame.Rect(0, 0, 1152, 648)
    assert presentation.surface.get_size() == (1152, 648)
    assert presentation.density == 1.0
    assert presentation.bars == ()


def test_the_bars_cover_exactly_the_window_outside_the_presented_rect() -> None:
    presentation = _presentation((2560, 1440))
    covered = sum(bar.width * bar.height for bar in presentation.bars)
    window_area = 2560 * 1440
    assert covered + presentation.rect.width * presentation.rect.height == window_area


def test_present_writes_the_viewport_and_flips() -> None:
    presentation = _presentation((1920, 1080))
    presentation.surface.fill((10, 20, 30))
    presentation.present()
    # The presented region of the window carries the viewport's colour.
    pixel = presentation.stage.get_at((presentation.rect.centerx, presentation.rect.centery))
    assert pixel[:3] == (10, 20, 30)


def test_the_bars_are_black_and_the_stale_frame_does_not_survive_a_resize() -> None:
    """After a shrink, the old image must not linger in the new bars."""
    stage = FakeStage((2560, 1440))
    presentation: Any = Presentation(stage.surface, FRAMING)
    presentation.surface.fill((200, 100, 50))
    presentation.present()

    stage.surface = pygame.Surface((1920, 1080))
    assert presentation.retarget(stage.surface), "a smaller window must produce a new target"
    presentation.surface.fill((200, 100, 50))
    presentation.present()

    for bar in presentation.bars:
        assert bar.width > 0 and bar.height > 0
        assert stage.surface.get_at((bar.centerx, bar.centery))[:3] == (0, 0, 0)


@pytest.mark.parametrize("window", WINDOWS)
def test_the_picture_reaches_the_window_unchanged(window: tuple[int, int]) -> None:
    """Not "the right colour in the middle": the same bytes, everywhere.

    A ``smoothscale`` anywhere between the target and the screen would keep a
    flat fill looking correct and only break on detail, so the check is on the
    whole buffer: every pixel the game drew is the pixel the screen has.
    """
    presentation = _presentation(window)
    surface = presentation.surface
    for y in range(0, surface.get_height(), 5):
        pygame.draw.line(
            surface, (y % 256, 60, 200 - y % 200), (0, y), (surface.get_width() - 1, y)
        )

    presentation.present()

    shown = presentation.stage.subsurface(presentation.rect)
    assert pygame.image.tobytes(shown, "RGB") == pygame.image.tobytes(surface, "RGB")


def test_a_degenerate_window_does_not_divide_by_zero() -> None:
    """A window of nothing still has to produce a surface someone can draw on."""
    presentation = _presentation((0, 0))
    assert presentation.rect.width >= 1 and presentation.rect.height >= 1
    assert presentation.density > 0.0
    assert presentation.recompute() is False


class CountingSurface(pygame.Surface):
    """A window surface that remembers how often it was filled."""

    def __init__(self, size: tuple[int, int]) -> None:
        super().__init__(size)
        self.fills = 0

    def fill(self, *args: Any, **kwargs: Any) -> None:
        self.fills += 1
        super().fill(*args, **kwargs)


def test_the_bars_are_painted_once_and_not_every_frame() -> None:
    """Repainting black over black is the cost this stopped paying.

    The strips used to be filled on every single frame, which is a second full
    pass over 1.27 million pixels on a 3440x1440 window -- 0.69ms, measured,
    for a colour the window already held. ``present`` now fills them when they
    have moved and not otherwise, so this counts rather than trusts.
    """
    window = (3440, 1440)
    stage = CountingSurface(window)
    presentation = Presentation(stage, FRAMING)
    assert presentation.bars, "a 21:9 window is the shape this is about"

    presentation.present()
    after_first = stage.fills
    assert after_first == len(presentation.bars)

    for _ in range(10):
        presentation.present()
    assert stage.fills == after_first, "the strips were repainted under a window that stood still"


def test_the_bars_are_repainted_when_the_rect_moves_but_its_size_does_not() -> None:
    """The strip cache is keyed on the whole rect, and this is why.

    ``Game._retarget`` calls ``recompute`` directly and never ``retarget``, so
    this path leaves the cache alone and relies on it: SDL resizes the window
    surface in place for a ``VIDEORESIZE``, and a 16:9 window dragged taller
    keeps its fitted width -- the rectangle keeps its size and slides down.
    Keyed on the size, as ``recompute`` itself is, the cache would look unchanged
    and skip the paint, leaving the newly exposed strips holding the frame that
    was on screen before the drag. That is the bug the strips exist to prevent,
    reintroduced by optimising them away.

    The size genuinely is unchanged here, which is the point: asserting only
    that the strips are black after a resize passes against a size-keyed cache,
    because a fresh surface has been filled anyway.
    """
    presentation: Any = Presentation(CountingSurface((1920, 1080)), FRAMING)
    assert presentation.bars == (), "a 16:9 window starts with nothing to paint"
    stage = presentation.stage
    stage.fill((200, 100, 50))
    presentation.surface.fill((200, 100, 50))
    presentation.present()

    # The window the player dragged: SDL keeps the pixels it had, which is the
    # whole reason the strips are painted, so the simulation copies the frame
    # across rather than handing over an empty surface.
    grown = CountingSurface((1920, 1200))
    grown.blit(stage, (0, 0))
    presentation.stage = grown
    presentation.recompute()
    presentation.surface.fill((200, 100, 50))
    presentation.present()

    assert presentation.rect.size == (1920, 1080), "the fitted size is what must not change"
    assert presentation.rect.y > 0, "a taller window slides the picture down"
    assert presentation.bars, "a taller window has strips"
    assert grown.get_at((960, 1))[:3] == (0, 0, 0), (
        "the strip kept the frame the window had before the drag"
    )
    assert grown.get_at((960, presentation.rect.centery))[:3] == (200, 100, 50), (
        "the picture still has to arrive under it"
    )
