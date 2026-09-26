"""The video screen has to be usable with a mouse, not only with a keyboard.

Six of its nine rows used to highlight on a click and then do nothing: the focus
moved, so the click looked like it had landed, and the value only changed if you
then pressed a direction or Enter. A dead row that highlights is worse than one
that stays grey, because it answers back.

These tests click, the way a pointer does -- at the rectangle the view actually
drew -- rather than calling the cyclers directly, so a row that is unreachable
by mouse cannot pass by having a working key binding.
"""

from types import SimpleNamespace

import pygame
import pytest

from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import UserSettings
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.mode import DisplayMode
from src.core.display.viewport import Viewport
from src.core.input.event_router import InputDevice, RoutedInput
from src.core.input.input_actions import InputAction

#: Rows that do something of their own rather than cycling a value.
ACTION_ROWS = frozenset({"size", "reset", "back"})

#: Rows whose value is a yes/no. Everything else in ``CYCLING_ROWS`` is a list.
BOOLEAN_ROWS = frozenset({"smoothing", "vsync"})


def _game(display: DisplayMode = DisplayMode.WINDOW) -> SimpleNamespace:
    game = SimpleNamespace(
        settings=UserSettings().with_video(display=display),
        scene_manager=SimpleNamespace(push=lambda _: None, pop=lambda: None),
        # No window yet, which the screen handles: the cost hint is about a
        # window that is too large, and there is not one to be large.
        stage=None,
    )

    def apply_settings(settings: UserSettings) -> None:
        game.settings = settings

    game.apply_settings = apply_settings
    return game


def _click(scene: VideoScene, index: int) -> str | None:
    """Press the row the way a pointer does: at the rectangle the view drew."""
    centre = scene.view.item_rects[index].center
    return scene.handle_routed(
        RoutedInput(InputAction.UI_POINTER_DOWN, InputDevice.MOUSE, position=centre)
    )


def _drawn(display: DisplayMode = DisplayMode.WINDOW) -> VideoScene:
    """A scene whose view has laid out, so its row rectangles exist."""
    pygame.init()
    scene = VideoScene(_game(display))
    scene.draw(Viewport(DEFAULT_FRAMING, 1).surface)
    return scene


def _row(scene: VideoScene, action: str) -> int:
    return next(index for index, item in enumerate(scene.model.items) if item.action == action)


def _focus(scene: VideoScene, index: int) -> None:
    """Walk the selection onto a row with the down key, as a player would."""
    for _ in range(index):
        scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    assert scene.model.current_item is not None
    assert scene.model.current_item.action == scene.model.items[index].action


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    pygame.init()
    if not pygame.display.get_surface():
        pygame.display.set_mode((320, 240))


@pytest.mark.parametrize("action", VideoScene.CYCLING_ROWS)
def test_a_click_steps_the_row(action: str) -> None:
    scene = _drawn()
    before = scene.game.settings

    assert _click(scene, _row(scene, action)) is not None
    assert scene.game.settings != before, f"a click on {action!r} changed nothing"


@pytest.mark.parametrize("action", VideoScene.CYCLING_ROWS)
def test_a_click_on_a_boolean_row_toggles_it(action: str) -> None:
    """A click has no direction, so on a yes/no row it has to flip.

    Setting the value instead made the row answer only when it disagreed with
    the click, which is a row that looks dead half the time.
    """
    if action not in BOOLEAN_ROWS:
        pytest.skip(f"{action!r} is a list, not a yes/no")
    scene = _drawn()
    first = _click(scene, _row(scene, action))
    once = scene.game.settings
    _click(scene, _row(scene, action))

    assert first is not None
    assert scene.game.settings != once, "two clicks must cancel out"
    assert scene.game.settings == _drawn().game.settings


@pytest.mark.parametrize(
    "action", tuple(a for a in VideoScene.CYCLING_ROWS if a not in BOOLEAN_ROWS)
)
def test_a_click_steps_a_list_row_like_the_right_key(action: str) -> None:
    """The two paths are one implementation, so they cannot drift again."""
    by_click = _drawn()
    _click(by_click, _row(by_click, action))

    by_key = _drawn()
    _focus(by_key, _row(by_key, action))
    by_key.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.KEYBOARD))

    assert by_click.game.settings == by_key.game.settings


def test_every_row_does_something() -> None:
    """No row may be outside both lists.

    This is the check that names the bug: the rows were split between one that
    a click reached and one that a key reached, and a row in neither is
    invisible until someone tries it.
    """
    scene = _drawn()
    reachable = set(VideoScene.CYCLING_ROWS) | ACTION_ROWS

    assert {item.action for item in scene.model.items} <= reachable


def test_the_size_row_opens_the_picker() -> None:
    pushed: list[object] = []
    scene = _drawn()
    scene.game.scene_manager.push = pushed.append

    _click(scene, _row(scene, "size"))

    assert len(pushed) == 1


def test_the_reset_row_resets() -> None:
    scene = _drawn()
    scene.game.settings = scene.game.settings.with_video(smoothing=False)
    before = scene.game.settings

    _click(scene, _row(scene, "reset"))

    assert scene.game.settings != before


def test_the_back_row_leaves() -> None:
    calls: list[str] = []
    scene = _drawn()
    scene.game.scene_manager.pop = lambda: calls.append("pop")

    _click(scene, _row(scene, "back"))

    assert calls == ["pop"]


def test_the_size_row_is_unavailable_without_a_window() -> None:
    """Borderless owns the size, so the row says so instead of pretending."""
    scene = _drawn(DisplayMode.BORDERLESS)

    assert not scene.model.items[_row(scene, "size")].enabled
