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
    raise FileNotFoundError(
        f"{path} is missing. The font is versioned with the assets; a checkout "
        "without it has no interface, and a system-font fallback would make "
        "every machine answer differently."
    )


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


#: The player-facing menus' font: Press Start 2P (SIL OFL 1.1, licence in
#: ``assets/fonts/PressStart2P-OFL.txt``). A pixel font drawn on an 8px grid, so
#: it is sharp only at multiples of 8 and only without antialiasing -- see
#: :func:`menu_font_size`. The debug layer keeps the monospace above.
_MENU = _FONTS_DIR / "PressStart2P-Regular.ttf"

#: The font's pixel grid.
MENU_FONT_GRID = 8

_MENU_CACHE: dict[int, pygame.font.Font] = {}


def menu_font_size(design: float, scale: float) -> int:
    """A design size at ``scale``, snapped to the font's grid and never below it."""
    return max(MENU_FONT_GRID, round(design * scale / MENU_FONT_GRID) * MENU_FONT_GRID)


def menu_font(size: int) -> pygame.font.Font:
    """The menu font at ``size`` pixels, built once. It has a single weight."""
    cached = _MENU_CACHE.get(size)
    if cached is None:
        cached = _load(_MENU, size)
        _MENU_CACHE[size] = cached
    return cached
