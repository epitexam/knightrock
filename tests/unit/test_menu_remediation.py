"""Regressions from the display/menu audit: stack drawing, panel width, focus, fit label."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.application.scene import Scene
from src.application.scene_manager import SceneManager
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1280, 720))


def test_moving_the_selection_does_not_move_the_panel() -> None:
    """The ``>`` marker sits in a reserved gutter, so the panel keeps its place."""
    surface = pygame.Surface((1280, 720))
    model = MenuModel(
        [MenuItem("a", "A"), MenuItem("long", "A much longer label"), MenuItem("b", "B")]
    )
    view = MenuView()
    first = view.draw(surface, "TITLE", model, top=150)
    model.move(1)
    second = view.draw(surface, "TITLE", model, top=150)

    assert first == second


def test_a_value_getting_shorter_does_not_shrink_the_panel() -> None:
    surface = pygame.Surface((1280, 720))
    view = MenuView()
    wide = view.draw(
        surface, "T", MenuModel([MenuItem("v", "VSync", "on · requested 144 Hz")]), top=150
    )
    narrow = view.draw(surface, "T", MenuModel([MenuItem("v", "VSync", "off")]), top=150)

    assert narrow.width == wide.width


def test_a_row_too_wide_for_the_window_stays_inside_the_panel() -> None:
    surface = pygame.Surface((640, 360))
    model = MenuModel([MenuItem("v", "Frame limit", "a value far too long " * 6)])
    view = MenuView()
    panel = view.draw(surface, "T", model, top=150)

    assert panel.right <= surface.get_width()
    assert all(panel.contains(rect) for rect in view.item_rects if rect.width)


def test_the_top_follows_the_picture_height() -> None:
    model = MenuModel([MenuItem("a", "A")])
    small = MenuView().draw(pygame.Surface((1152, 648)), "T", model, top=150)
    large = MenuView().draw(pygame.Surface((2304, 1296)), "T", model, top=150)

    assert large.top == 2 * small.top


class _Panel(Scene):
    def __init__(self, game, log, name, **flags) -> None:
        super().__init__(game)
        self.log, self.name = log, name
        for key, value in flags.items():
            setattr(self, key, value)

    def update(self, delta_time: float) -> None:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        self.log.append(self.name)


def _manager() -> SceneManager:
    game = SimpleNamespace(
        input_router=SimpleNamespace(reset=lambda: None), events=None, ui_scale=1.0
    )
    return SceneManager(game)


def test_a_menu_page_hides_the_menu_panels_below_it() -> None:
    manager, log = _manager(), []
    manager._stack = [
        _Panel(None, log, "menu", opaque=True),
        _Panel(None, log, "options", covers_panels_below=True),
        _Panel(None, log, "video", covers_panels_below=True),
    ]
    manager.draw(pygame.Surface((64, 36)))

    assert log == ["video"]


def test_a_menu_page_over_the_game_keeps_the_world_behind_it() -> None:
    manager, log = _manager(), []
    manager._stack = [
        _Panel(None, log, "world", opaque=True, is_backdrop=True),
        _Panel(None, log, "pause"),
        _Panel(None, log, "options", covers_panels_below=True),
    ]
    manager.draw(pygame.Surface((64, 36)))

    assert log == ["world", "options"]


def test_an_overlay_is_still_drawn_over_the_game() -> None:
    manager, log = _manager(), []
    manager._stack = [
        _Panel(None, log, "world", opaque=True, is_backdrop=True),
        _Panel(None, log, "pause"),
    ]
    manager.draw(pygame.Surface((64, 36)))

    assert log == ["world", "pause"]
