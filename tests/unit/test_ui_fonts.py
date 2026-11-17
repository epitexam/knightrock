"""The interface answers from a font the repository ships.

``pygame.font.SysFont`` resolves a *name*, and the name it was given -- a
Windows font -- does not exist on most machines. Every one of them answered
with a different substitute, so the debug panels, the menus and the goldens
were all machine-dependent: the suite was red on a machine without Consolas
and the code was not wrong. It was under-determined.

The fix is one factory that loads a file versioned with the assets, so the
answer is the same on every machine, in CI and inside the PyInstaller bundle.
"""

import os

import pygame
import pytest

from src.core.paths import PROJECT_ROOT
from src.ui.fonts import menu_font

FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


def test_the_font_it_loads_is_the_one_that_is_shipped() -> None:
    shipped = FONTS_DIR / "PressStart2P-Regular.ttf"
    assert shipped.is_file(), f"{shipped.name} is not in the repository"
    assert menu_font(16).get_height() == pygame.font.Font(str(shipped), 16).get_height()


def test_a_pixel_size_is_built_once_and_shared() -> None:
    assert menu_font(16) is menu_font(16)


def test_the_interface_does_not_resolve_a_font_by_system_name() -> None:
    """A SysFont call site is a new machine-dependent answer."""
    for path in sorted((PROJECT_ROOT / "src" / "ui").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "SysFont(" not in source, (
            f"{path.name} resolves a font by system name; use src.ui.fonts.menu_font, "
            "which answers from the bundled file"
        )
