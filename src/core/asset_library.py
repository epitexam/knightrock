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
        self._frame_cache: dict[str, list[pygame.Surface]] = {}

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

    def frames(self, relative_directory: str | Path) -> list[pygame.Surface]:
        """Return the cached converted frame list for a sprite-sheet directory.

        A "sprite sheet" here is a directory of numbered PNG frames
        (``0.png``, ``1.png``, ...) — the layout shipped under
        ``assets/graphics/{player,enemies,items}/<animation>/``.
        Frames are sorted numerically and served in a shared, converted
        state: callers must never mutate them.

        If the requested directory doesn't exist, falls back to "run" for
        player animations (graceful degradation when dash assets aren't
        available yet). For other cases, raises FileNotFoundError.

        A fallback is cached under the key that was *asked for* as well as
        the one it resolved to. The recursion returns the fallback's frames,
        but the requester's key was never populated, so every subsequent call
        repeated the ``is_dir()`` that discovered the fallback in the first
        place -- a stat syscall per call, per animation, per frame, for as
        long as the game ran.

        Parameters
        ----------
        relative_directory : str | Path
            Directory relative to the project root (or PyInstaller bundle
            root), e.g. ``"assets/graphics/player/idle"``.

        Raises
        ------
        FileNotFoundError
            If the directory does not exist and no fallback is available,
            or contains no frames.
        """
        key = f"f:{relative_directory}"
        cached = self._frame_cache.get(key)
        if cached is not None:
            return cached

        directory = Path(resource_path(str(relative_directory)))
        if not directory.is_dir():
            fallback = self._fallback_directory(relative_directory)
            if fallback is None:
                raise FileNotFoundError(f"Animation directory not found: {directory}")
            frames = self.frames(fallback)
            self._frame_cache[key] = frames
            return frames

        def frame_order(path: Path) -> tuple[int, str]:
            """Numbered frames sort numerically ('10' after '2'); names last."""
            return (0, path.stem.zfill(8)) if path.stem.isdigit() else (1, path.stem)

        frame_paths = sorted(
            (p for p in directory.iterdir() if p.suffix.lower() == ".png"),
            key=frame_order,
        )
        if not frame_paths:
            raise FileNotFoundError(f"No PNG frames in animation directory: {directory}")

        frames = [self.image(frame_path) for frame_path in frame_paths]
        self._frame_cache[key] = frames
        return frames

    @staticmethod
    def _fallback_directory(relative_directory: str | Path) -> str | None:
        """The directory to serve when the requested one is absent, or None.

        Only player animations degrade, and only where the reuse is readable:
        ``dash`` -> ``run`` (a dash reusing the run frames animates) and
        ``crouch`` -> ``idle`` (a crouch reusing the idle frames at least stays
        on the ground instead of animating a run cycle in place). A missing
        frameset for any other animation is a broken asset and should say so.
        """
        name = str(relative_directory)
        for animation, fallback in (
            ("player/dash", "player/run"),
            ("player/crouch", "player/idle"),
        ):
            if animation in name:
                return name.replace(animation, fallback)
        return None

    def clear(self) -> None:
        """Drop the whole cache (level transition or memory pressure)."""
        self._cache.clear()
        self._frame_cache.clear()


_SHARED_LIBRARY: AssetLibrary | None = None


def shared_library() -> AssetLibrary:
    """Return the process-wide lazy :class:`AssetLibrary`.

    Created on first use (not at import time) so ``convert_alpha`` always
    runs after the display is initialized — headless tests initialize the
    dummy driver in a session fixture first.
    """
    global _SHARED_LIBRARY
    if _SHARED_LIBRARY is None:
        _SHARED_LIBRARY = AssetLibrary()
    return _SHARED_LIBRARY
