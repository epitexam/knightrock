"""The font the interface paints with, loaded from a bundled file.

``SysFont`` answers from whatever the machine happens to have installed: the
game asked for ``Consolas``, a Windows font, and every machine that does not
carry it silently gets a different one -- different metrics, different layout,
different goldens. The debug panels and the menus were machine-dependent, and
the CI fell over on it without the code being wrong.

The file is versioned with the rest of ``assets/``, so the answer is the same
on every machine and inside the PyInstaller bundle. It is a monospace on
purpose: the debug layer prints columns, and a proportional font makes them
drift apart line by line.
"""

from pathlib import Path

import pygame

from src.core.paths import resource_path

_FONTS_DIR = Path(resource_path("assets/fonts"))
_REGULAR = _FONTS_DIR / "LiberationMono-Regular.ttf"
_BOLD = _FONTS_DIR / "LiberationMono-Bold.ttf"

#: ``size -> (regular, bold)``.
_CACHE: dict[int, tuple[pygame.font.Font, pygame.font.Font]] = {}


def _load(path: Path, size: int) -> pygame.font.Font:
    if path.is_file():
        return pygame.font.Font(str(path), size)
    return pygame.font.SysFont("monospace", size, bold=path is _BOLD)


def ui_fonts(size: int) -> tuple[pygame.font.Font, pygame.font.Font]:
    """The two weights at one pixel size, built once and reused.

    A ``Font`` object is a surface holder, and rebuilding it per call is the
    cost the call-site caches existed to avoid; they each built their own dict,
    so this keeps the same shape with one cache instead of three.
    """
    cached = _CACHE.get(size)
    if cached is None:
        cached = (_load(_REGULAR, size), _load(_BOLD, size))
        _CACHE[size] = cached
    return cached


def ui_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    return ui_fonts(size)[1 if bold else 0]
