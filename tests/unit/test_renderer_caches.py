"""The shear cache must not hand back a surface sized for another source."""

import pygame

from src.core.rendering.renderer import _SHEAR_CACHE, _sheared


def _source(size: tuple[int, int], color: tuple[int, int, int, int]) -> pygame.Surface:
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill(color)
    return surface


def test_a_source_freed_under_its_key_does_not_reuse_the_stale_shear() -> None:
    _SHEAR_CACHE.clear()
    _sheared(_source((32, 40), (200, 60, 60, 255)), 6)
    key = next(iter(_SHEAR_CACHE))

    big = _source((70, 60), (60, 200, 60, 255))
    _SHEAR_CACHE[key] = (big, _SHEAR_CACHE[key][1])

    answer = _sheared(big, 6)
    assert answer.get_size() == (76, 60)
    assert answer is not _SHEAR_CACHE[key][1]


def test_the_cache_holds_the_source_its_value_was_built_from() -> None:
    _SHEAR_CACHE.clear()
    source = _source((32, 40), (200, 60, 60, 255))
    _sheared(source, 6)
    assert all(held is not None for held, _ in _SHEAR_CACHE.values())
