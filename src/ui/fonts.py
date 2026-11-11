"""The font the interface paints with, loaded from a bundled file.

Press Start 2P (SIL OFL 1.1, licence in ``assets/fonts/PressStart2P-OFL.txt``):
the menus, the HUD and the debug panels all draw with it. It is versioned with
the assets, so the answer is the same on every machine and inside the
PyInstaller bundle -- ``SysFont`` answers from whatever the machine has
installed, and made the interface and its goldens machine-dependent. It is also
monospaced, which the debug panels' columns rely on.
"""

from pathlib import Path

import pygame

from src.core.paths import resource_path

_FONTS_DIR = Path(resource_path("assets/fonts"))


def _load(path: Path, size: int) -> pygame.font.Font:
    if path.is_file():
        return pygame.font.Font(str(path), size)
    raise FileNotFoundError(
        f"{path} is missing. The font is versioned with the assets; a checkout "
        "without it has no interface, and a system-font fallback would make "
        "every machine answer differently."
    )


#: Drawn on an 8px grid, so sharp only at multiples of 8 and only without
#: antialiasing -- see :func:`menu_font_size`.
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
