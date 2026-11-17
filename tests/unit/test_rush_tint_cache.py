"""The full-screen rush tint is reused, not rebuilt every frame."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.core.rendering.strike_trails import (
    _RUSH_TINT_CACHE_MAX,  # noqa: SLF001 - the bound under test
    RUSH_FADE,
    RUSH_TINT,
    StrikeTrails,
)


def _trail_with_rush(size: tuple[int, int]) -> tuple[StrikeTrails, pygame.Surface]:
    trails = StrikeTrails()
    trails._rushing[1] = 0.1  # noqa: SLF001 - the effect under test
    return trails, pygame.Surface(size, pygame.SRCALPHA)


def test_the_tint_is_cached_per_size_and_alpha() -> None:
    pygame.display.set_mode((320, 240))
    trails, surface = _trail_with_rush((320, 240))

    trails._draw_rush_tint(surface)  # noqa: SLF001 - the effect under test
    first = next(iter(trails._rush_tints.values()))  # noqa: SLF001
    trails._draw_rush_tint(surface)  # noqa: SLF001
    second = next(iter(trails._rush_tints.values()))  # noqa: SLF001

    assert first is second
    assert len(trails._rush_tints) == 1  # noqa: SLF001


def test_a_resize_gets_its_own_tint_without_changing_the_old_one() -> None:
    pygame.display.set_mode((320, 240))
    trails, small = _trail_with_rush((320, 240))
    large = pygame.Surface((640, 480), pygame.SRCALPHA)

    trails._draw_rush_tint(small)  # noqa: SLF001
    trails._draw_rush_tint(large)  # noqa: SLF001

    assert len(trails._rush_tints) == 2  # noqa: SLF001
    assert all(tint.get_size() in ((320, 240), (640, 480)) for tint in trails._rush_tints.values())  # noqa: SLF001
    assert RUSH_TINT[3] > 0


def test_the_tint_cache_is_bounded() -> None:
    """A fade must not pin one full-screen surface per possible alpha."""
    pygame.display.set_mode((320, 240))
    trails, surface = _trail_with_rush((320, 240))

    for alpha in range(RUSH_TINT[3] + 10):
        trails._rushing[1] = RUSH_FADE * alpha / RUSH_TINT[3]  # noqa: SLF001
        trails._draw_rush_tint(surface)  # noqa: SLF001

    assert len(trails._rush_tints) <= _RUSH_TINT_CACHE_MAX  # noqa: SLF001


def test_clear_tints_drops_every_entry() -> None:
    pygame.display.set_mode((320, 240))
    trails, surface = _trail_with_rush((320, 240))
    trails._draw_rush_tint(surface)  # noqa: SLF001

    trails.clear_tints()

    assert not trails._rush_tints  # noqa: SLF001
