"""Regressions from the display/menu audit: stack drawing, panel width, focus, fit label."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.application.scene import Scene
from src.application.scene_manager import SceneManager


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1280, 720))


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
