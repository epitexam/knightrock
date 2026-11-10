"""Regressions from the display/menu audit: stack drawing, panel width, focus, fit label."""

import os
from dataclasses import replace
from types import SimpleNamespace

import pygame
import pytest

from src.application.scene import Scene
from src.application.scene_manager import SceneManager
from src.application.scenes.option_screen import OptionScreen
from src.application.scenes.video_options import window_size_options
from src.application.scenes.video_scene import VideoScene
from src.core.display.letterbox import FitPolicy
from src.core.display.monitors import Monitor
from src.core.input.event_router import InputDevice, RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.menu_model import MenuItem, MenuModel
from src.ui.menu_view import MenuView
from tests.unit.test_video_scene import _game


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


def test_the_focus_comes_back_to_the_row_that_opened_the_list() -> None:
    game = _game()
    pushed: list = []
    game.scene_manager = SimpleNamespace(push=pushed.append, pop=lambda: None)
    scene = VideoScene(game)
    scene.draw(pygame.Surface((2304, 1296)))
    while scene.model.current_item.action != "frame_limit":
        scene.model.move(1)
    scene.handle_routed(RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD))
    screen = pushed[-1]
    assert isinstance(screen, OptionScreen)

    screen._choose(0)

    assert scene.model.current_item.action == "frame_limit"


def test_the_fit_row_reports_the_policy_in_force() -> None:
    """A migrated file with whole-pixel art on and no policy draws in integer."""
    game = _game()
    game.settings = replace(game.settings, pixel_perfect=True, fit=FitPolicy.BARS)
    scene = VideoScene(game)
    fit = next(item for item in scene.model.items if item.action == "fit")

    assert fit.value == FitPolicy.INTEGER.value


def test_two_sizes_of_the_same_area_sort_without_error() -> None:
    monitor = Monitor(0, "", (0, 0, 3840, 2160), (0, 0, 3840, 2160))
    options = window_size_options(monitor, (1500, 1000), (1500, 1000))

    assert options[0].value is None


def test_a_row_that_does_nothing_is_refused_when_declared() -> None:
    """The dead row: drawn, aimable, and inert. The table refuses to hold one."""
    from src.application.scenes.video_scene import Row

    with pytest.raises(ValueError):
        Row("nothing", "Does nothing")
    with pytest.raises(ValueError):
        Row("both", "Two jobs", toggle="vsync", readout=True)


def test_every_video_row_is_declared_once() -> None:
    actions = [row.action for row in VideoScene.ROWS]

    assert len(actions) == len(set(actions))
    assert set(VideoScene.SUBMENUS) <= set(actions)


def test_auto_takes_whole_pixels_when_they_keep_most_of_the_picture() -> None:
    from src.core.display.letterbox import picture

    # 2400x1350 holds a 2x picture (2304x1296): 92% of the bars picture, exact pixels.
    auto = picture((2400, 1350), policy=FitPolicy.AUTO)
    assert auto.dest.size == picture((2400, 1350), policy=FitPolicy.INTEGER).dest.size


def test_auto_takes_bars_when_whole_pixels_would_leave_a_small_box() -> None:
    from src.core.display.letterbox import picture

    # 2200x1238 only holds 1x (1152x648): a quarter of the window.
    auto = picture((2200, 1238), policy=FitPolicy.AUTO)
    assert auto.dest.size == picture((2200, 1238), policy=FitPolicy.BARS).dest.size


def test_auto_is_the_default_and_an_old_whole_pixel_flag_still_wins() -> None:
    from src.application.settings_store import UserSettings
    from src.core.display.letterbox import effective_fit

    assert UserSettings().fit is FitPolicy.AUTO
    assert effective_fit(FitPolicy.AUTO, pixel_perfect=True) is FitPolicy.INTEGER
    assert effective_fit(FitPolicy.ZOOM, pixel_perfect=True) is FitPolicy.ZOOM
