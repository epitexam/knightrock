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


def test_menu_view_recalculates_geometry_after_surface_change() -> None:
    model = MenuModel([MenuItem("one", "One"), MenuItem("two", "Two")])
    view = MenuView()
    first_surface = pygame.Surface((640, 480))
    second_surface = pygame.Surface((1280, 720))
    view.draw(first_surface, "TITLE", model, top=120)
    first_rects = view.item_rects
    second_panel = view.draw(second_surface, "TITLE", model, top=120)
    second_rects = view.item_rects

    assert first_rects != second_rects
    assert all(second_panel.contains(rect) for rect in second_rects)
    assert not all(second_panel.contains(rect) for rect in first_rects)


def test_menu_view_changes_geometry_with_scale() -> None:
    surface = pygame.display.get_surface()
    model = MenuModel([MenuItem("one", "One")])

    normal = MenuView().draw(surface, "TITLE", model, top=120)
    large = MenuView(1.2).draw(surface, "TITLE", model, top=120)

    assert large.width >= normal.width
    assert large.height >= normal.height
