import os

import pygame
import pytest

from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


def test_menu_view_returns_item_rects_inside_panel() -> None:
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    view = MenuView()

    panel = view.draw(surface, "TITLE", model, top=120)

    assert panel.width > 0
    assert len(view.item_rects) == 2
    assert all(panel.contains(rect) for rect in view.item_rects)


def test_menu_view_changes_geometry_with_scale() -> None:
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem("one", "One")])

    normal = MenuView().draw(surface, "TITLE", model, top=120)
    large = MenuView(1.2).draw(surface, "TITLE", model, top=120)

    assert large.width >= normal.width
    assert large.height >= normal.height
