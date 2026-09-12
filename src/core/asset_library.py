"""Nascent lazy asset loading with display-format conversion (audit F4.1, Phase 1 #3).

Entities currently render colored rectangles. The shipped art (a hundred
spritesheets under ``assets/graphics/``) is unused. This module is the
foundation of the future ``AssetLibrary`` (Phase 2 #1: ``Animator``,
per-state sprite sheets): it loads each image once and converts it to the
display format so blits are fast.
"""

from pathlib import Path

import pygame

from src.core.paths import resource_path


class AssetLibrary:
    """Lazy, cached loader of images converted to the display format.

    ``image()`` loads each file once, converts it with
    :meth:`pygame.Surface.convert_alpha` (or :meth:`pygame.Surface.convert`
    for fully-opaque images), then serves the cached surface.
    Surfaces are shared: callers must never mutate them.
    """

    def __init__(self) -> None:
        self._cache: dict[str, pygame.Surface] = {}

    def image(self, relative_path: str | Path, *, alpha: bool = True) -> pygame.Surface:
        """Return the cached converted surface for ``relative_path``.

        Parameters
        ----------
        relative_path : str | Path
            Path relative to the project root (or PyInstaller bundle root),
            e.g. ``"assets/graphics/player/idle/0.png"``.
        alpha : bool
            Use ``convert_alpha`` (per-pixel alpha) when True, plain
            ``convert`` otherwise.

        Raises
        ------
        pygame.error
            If the image cannot be decoded.
        OSError
            If the file does not exist or cannot be read.
        """
        key = f"{'a' if alpha else 's'}:{relative_path}"
        surface = self._cache.get(key)
        if surface is not None:
            return surface

        raw = pygame.image.load(resource_path(str(relative_path)))
        surface = raw.convert_alpha() if alpha else raw.convert()
        self._cache[key] = surface
        return surface

    def preload(self, relative_paths: list[str | Path]) -> None:
        """Warm the cache for a batch of paths."""
        for relative_path in relative_paths:
            self.image(relative_path)

    def clear(self) -> None:
        """Drop the whole cache (level transition or memory pressure)."""
        self._cache.clear()
