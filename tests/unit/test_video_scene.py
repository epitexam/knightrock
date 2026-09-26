"""The video screen has to be usable with a mouse, not only with a keyboard.

Six of its nine rows used to highlight on a click and then do nothing: the focus
moved, so the click looked like it had landed, and the value only changed if you
then pressed a direction or Enter. A dead row that highlights is worse than one
that stays grey, because it answers back.

These tests click, the way a pointer does -- at the rectangle the view actually
drew -- rather than calling the cyclers directly, so a row that is unreachable
by mouse cannot pass by having a working key binding.

The screen has one row fewer than it had, and the one that went is the reason
this file is short: there is no resolution any more. What replaced it is a
read-out of the window, which no pointer and no key can change.
"""

from types import SimpleNamespace

import pygame
import pytest

from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import UserSettings
from src.core.display.mode import DisplayMode
from src.core.input.event_router import InputDevice, RoutedInput
from src.core.input.input_actions import InputAction

#: Rows that do something of their own rather than cycling a value.
ACTION_ROWS = frozenset({"reset", "back"})

#: The one row that is a read-out: it reports what the game derived from the
#: window and is reachable by nothing. It has to be named here, because the
#: check below is "no row is outside both lists" and a row nobody can act on is
#: exactly the shape of the bug that started this file.
REPORT_ROWS = frozenset({"info"})

#: Rows whose value is a yes/no. Everything else in ``CYCLING_ROWS`` is a list.
#: It has to be the complement of the list rows: a boolean is *flipped* by a
#: click and *set* by a key, on purpose, so a boolean that leaked into the list
#: comparison would look like a drift between two paths that agree by design.
BOOLEAN_ROWS = frozenset({"pixel_perfect", "vsync"})
LIST_ROWS = frozenset(VideoScene.CYCLING_ROWS) - BOOLEAN_ROWS

#: A window with room for a whole multiple of the framing, so every row that can
#: be enabled is. The read-out row needs one to report at all.
WINDOW = (2304, 1296)


def _game(display: DisplayMode = DisplayMode.WINDOW) -> SimpleNamespace:
    game = SimpleNamespace(
        settings=UserSettings().with_video(display=display),
        scene_manager=SimpleNamespace(push=lambda _: None, pop=lambda: None),
        stage=SimpleNamespace(size=WINDOW),
        presentation=SimpleNamespace(
            stage=pygame.Surface(WINDOW),
            pixel_perfect=False,
            window_size=WINDOW,
            density=2.0,
        ),
        ui_scale=1.0,
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
    scene.draw(pygame.Surface((1152, 648)))
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


@pytest.mark.parametrize("action", sorted(LIST_ROWS))
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
    reachable = set(VideoScene.CYCLING_ROWS) | ACTION_ROWS | REPORT_ROWS

    assert {item.action for item in scene.model.items} <= reachable
    # And the three sets are disjoint, so a row cannot be quietly claimed by
    # two of them and left to whichever runs first.
    assert not set(VideoScene.CYCLING_ROWS) & ACTION_ROWS
    assert not REPORT_ROWS & (set(VideoScene.CYCLING_ROWS) | ACTION_ROWS)
    for item in scene.model.items:
        if item.action in REPORT_ROWS:
            assert not item.enabled, "a read-out row must not be actionable"


def test_no_row_opens_another_screen() -> None:
    """The resolution picker is gone and nothing replaced it.

    It was the last place in the game that could claim a size for the player's
    monitor. A click anywhere on this screen now either changes a value or does
    nothing, which is a much easier thing to hold to account.
    """
    pushed: list[object] = []
    scene = _drawn()
    scene.game.scene_manager.push = pushed.append

    for index, item in enumerate(scene.model.items):
        if not item.enabled:
            continue
        _click(scene, index)

    assert pushed == []


def test_the_reset_row_resets() -> None:
    scene = _drawn()
    scene.game.settings = scene.game.settings.with_video(pixel_perfect=True, vsync=True)
    before = scene.game.settings

    _click(scene, _row(scene, "reset"))

    assert scene.game.settings != before
    assert scene.game.settings.pixel_perfect is False
    assert scene.game.settings.vsync is False


def test_the_back_row_leaves() -> None:
    calls: list[str] = []
    scene = _drawn()
    scene.game.scene_manager.pop = lambda: calls.append("pop")

    _click(scene, _row(scene, "back"))

    assert calls == ["pop"]


def test_whole_pixel_art_is_unavailable_on_a_window_too_small_for_one() -> None:
    """The row that can be unavailable, and it says which it is.

    Whole-pixel art snaps the picture to a whole multiple of the framing, and a
    window narrower than the framing has none to snap to. The row is then off and
    labelled, rather than reading "off" on a window where it would do nothing --
    a row that claims a setting it cannot honour.
    """
    game = _game()
    game.presentation.window_size = (800, 600)
    game.stage = SimpleNamespace(size=(800, 600))
    scene = VideoScene(game)
    scene.draw(pygame.Surface((1152, 648)))

    item = scene.model.items[_row(scene, "pixel_perfect")]
    assert not item.enabled
    assert "too small" in item.value
