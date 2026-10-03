"""The video screen has to be usable with a mouse, not only with a keyboard.

Six of its nine rows used to highlight on a click and then do nothing: the focus
moved, so the click looked like it had landed, and the value only changed if you
then pressed a direction or Enter. A dead row that highlights is worse than one
that stays grey, because it answers back.

These tests click, the way a pointer does -- at the rectangle the view actually
drew -- rather than calling the cyclers directly, so a row that is unreachable
by mouse cannot pass by having a working key binding.

It was a click-only file for a while, and that is why the two yes/no rows shipped
with a dead key. ``_cycle_bool`` tested ``action is UI_RIGHT`` and treated every
other input as "the left key", so confirm -- the way a gamepad presses anything
-- set a boolean to off and could never set it to on. Every test here pressed a
mouse, so the whole file was green and both rows were unusable to a player
holding a controller. The keyboard section below is the other half of the same
claim, and the generic row test is the one that notices when a key is missing
from either half.

The screen has one row fewer than it had, and the one that went is the reason
this file is short: there is no resolution any more. What replaced it is a
read-out of the window, which no pointer and no key can change.
"""

from types import SimpleNamespace

import pygame
import pytest

from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import PANEL_SCALES, UserSettings
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


@pytest.fixture(autouse=True)
def _debug_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run this file with the overlay on, so the debug-only row exists.

    ``panel_scale`` is in ``CYCLING_ROWS``, and those tests are the check that
    every row in it answers every key -- so without the flag the row is absent
    from the model and ``_row`` raises ``StopIteration`` on it. Which is the
    right failure: it says the suite is exercising a row the screen is not
    showing, rather than quietly skipping one.

    The flag is per-test rather than per-module because the tests that assert the
    row is *absent* without it need the opposite, and a module-level
    ``setenv`` would be undone by neither.
    """
    monkeypatch.setenv("DEBUG", "1")


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
    scene.game.settings = scene.game.settings.with_video(
        pixel_perfect=True, vsync=True, panel_scale=0.4
    )
    before = scene.game.settings

    _click(scene, _row(scene, "reset"))

    assert scene.game.settings != before
    assert scene.game.settings.pixel_perfect is False
    assert scene.game.settings.vsync is False
    assert scene.game.settings.panel_scale == 1.0


def test_reset_puts_the_panel_scale_back_to_the_default_one() -> None:
    """The reset row is the only way back from the smallest rung.

    Shown here because a setting that can only be raised by hand is a setting with
    no way back: 0.4 is where the panels actually fit a small window, so it is a
    value a player will land on and stay on. ``panel_scale`` was added to the
    reset row without a test, which meant the reset could quietly stop covering it
    -- and it would look fine, because the value is legal, it just would not come
    back to 1.0.

    Every rung rather than one, since a reset that skipped a single value would
    still read as working.
    """
    for panel_scale in PANEL_SCALES:
        scene = _drawn()
        scene.game.settings = scene.game.settings.with_video(panel_scale=panel_scale)

        _click(scene, _row(scene, "reset"))

        assert scene.game.settings.panel_scale == 1.0, f"{panel_scale} did not reset"


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


# --- the keyboard half ------------------------------------------------------


def _press(scene: VideoScene, action: InputAction) -> None:
    """Send one key to the row the selection is on."""
    scene.handle_routed(RoutedInput(action, InputDevice.KEYBOARD))


def _starting_settings(action: str, key: InputAction) -> UserSettings:
    """The settings to press ``key`` on ``action`` from, so the press must show.

    Only the yes/no rows need this, and only for one key. A boolean row
    *assigns* on the arrows rather than toggling, on purpose, so ← on a row that
    already reads off correctly does nothing at all -- and "correctly nothing"
    is indistinguishable from "the key is missing" if you only look at the value
    afterwards. Starting ← from on, and → and confirm from off, gives every case
    a state the key has to move.

    The list rows ignore all of it: both directions always step, so any starting
    value works and they take the default.
    """
    if action not in BOOLEAN_ROWS:
        return _drawn().game.settings
    start_on = key is InputAction.UI_LEFT
    return _drawn().game.settings.with_video(**{action: start_on})


@pytest.mark.parametrize("action", VideoScene.CYCLING_ROWS)
@pytest.mark.parametrize("key", [InputAction.UI_LEFT, InputAction.UI_RIGHT, InputAction.UI_CONFIRM])
def test_every_value_row_answers_every_key(action: str, key: InputAction) -> None:
    """No value row may be reachable by one input and dead to another.

    This is the test that would have caught the bug this section exists for, and
    it is deliberately generic rather than per-row: a per-row test for each of
    three keys is three tests per row and a fourth row nobody adds one for. The
    claim is the same shape as ``test_every_row_does_something`` on the click
    side -- every row is covered, or the set of rows is not the one we think.

    The rows that are not value rows are absent on purpose. ``reset`` and
    ``back`` act on confirm and must do nothing on a direction, and ``info`` is
    a read-out; ``test_every_row_does_something`` already owns those.
    """
    scene = _drawn()
    scene.game.settings = _starting_settings(action, key)
    _focus(scene, _row(scene, action))
    before = scene.game.settings

    _press(scene, key)

    assert scene.game.settings != before, (
        f"{action!r} does not answer {key.value}: the key is missing from the row"
    )


@pytest.mark.parametrize("action", sorted(BOOLEAN_ROWS))
def test_a_confirm_toggles_a_boolean_row(action: str) -> None:
    """Confirm is a click: one discrete press with no direction to read a value from.

    It used to be handled as the left key, which set the row off every time --
    so a yes/no row could be turned off but never on, and only by the two inputs
    that do have a direction. With a gamepad, where confirm is how you press a
    button, that is the whole row.
    """
    scene = _drawn()
    index = _row(scene, action)

    _focus(scene, index)
    _press(scene, InputAction.UI_CONFIRM)
    after_first = getattr(scene.game.settings, action)

    _press(scene, InputAction.UI_CONFIRM)
    after_second = getattr(scene.game.settings, action)

    assert after_first is not _drawn().game.settings.__getattribute__(action), (
        f"the first confirm changed nothing on {action!r}"
    )
    assert after_first is not after_second, "and the second one did not put it back"


@pytest.mark.parametrize("action", sorted(BOOLEAN_ROWS))
def test_a_direction_still_sets_a_boolean_row(action: str) -> None:
    """← and → assign, and that asymmetry is on purpose.

    Worth pinning because it looks like the bug above. Toggling would make ← and
    → behave identically, which reads as one of the two being broken -- so the
    arrows assign and only the directionless presses toggle. A future pass that
    "unified" them would be undoing a decision, not fixing one.
    """
    on = _drawn()
    _focus(on, _row(on, action))
    _press(on, InputAction.UI_LEFT)

    off = _drawn()
    _focus(off, _row(off, action))
    _press(off, InputAction.UI_RIGHT)

    assert getattr(on.game.settings, action) is False, "← from on goes off, not back to on"
    assert getattr(off.game.settings, action) is True, "and → from off goes on"


@pytest.mark.parametrize("action", sorted(LIST_ROWS))
def test_a_confirm_steps_a_list_row_like_the_right_key(action: str) -> None:
    """The confirm fix must not have touched the rows that were already fine.

    A list has an order, so confirm advances it -- which is the same answer → was
    already giving, and is why confirm was a toggle only for the rows that have
    no order to step through.
    """
    by_confirm = _drawn()
    _focus(by_confirm, _row(by_confirm, action))
    _press(by_confirm, InputAction.UI_CONFIRM)

    by_right = _drawn()
    _focus(by_right, _row(by_right, action))
    _press(by_right, InputAction.UI_RIGHT)

    assert by_confirm.game.settings == by_right.game.settings


def test_the_window_read_out_can_never_be_focused() -> None:
    """The reachable half of the guard: the selection skips it, going down and up.

    Two independent things keep a confirm off that row -- ``move`` refuses to
    land on a disabled one and ``set_items`` snaps to the nearest enabled -- so
    a press can never arrive there from the keyboard or the pointer. Asserted by
    walking the whole list in both directions rather than by construction,
    because the claim is about the selection and not about the guard.
    """
    scene = _drawn()
    index = _row(scene, "info")
    assert not scene.model.items[index].enabled, "it is the disabled row we are guarding"

    for _ in range(len(scene.model.items) * 2):
        scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
        assert scene.model.current_item is not None
        assert scene.model.current_item.action != "info"
        scene.handle_routed(RoutedInput(InputAction.UI_UP, InputDevice.KEYBOARD))
        assert scene.model.current_item is not None
        assert scene.model.current_item.action != "info"


def test_a_confirm_on_a_disabled_row_is_swallowed() -> None:
    """The guard itself, for the focus state the selection cannot produce.

    ``_handle_row_value_navigation`` returns early on a disabled row rather than
    letting the press through, and the reason is in its docstring: the menu model
    answers an action on a disabled row by activating the nearest *enabled* one,
    so a confirm that reached it would change the display mode from a row that
    only reports the window.

    So the focus has to be put there by hand -- ``_current`` is the only way, and
    reaching into it is the point rather than a shortcut, because the state is
    unreachable and that is precisely the state the guard is for. The test above
    covers the half a player can reach; this one covers the half they cannot.
    """
    scene = _drawn()
    index = _row(scene, "info")
    scene.model._current = index
    before = scene.game.settings

    assert scene._handle_row_value_navigation(
        RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD)
    ), "the guard claims the press"

    assert scene.game.settings == before, "and the display mode is untouched"


# --- the two rows that were reported dead -----------------------------------


def test_the_vsync_row_reports_the_setting_when_the_driver_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row must answer the setting, with the driver's refusal as the caveat.

    It read ``off (unavailable)`` -- which answers "off" to a player who had just
    pressed something that did land, and is the same "the row is dead" symptom
    the confirm bug produced by a second route. Saying the driver refused is
    worth keeping; replacing the setting with the driver's opinion is not.
    """
    game = _game()
    game.settings = game.settings.with_video(vsync=True)
    scene = VideoScene(game)
    monkeypatch.setattr(VideoScene, "_vsync_is_active", staticmethod(lambda: False))

    label = scene._vsync_label()

    assert label.startswith("on"), f"the setting is on and the row says {label!r}"
    assert "not honoured" in label, "and still says the driver refused it"


def test_the_vsync_row_carries_no_caveat_when_it_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing was refused, because nothing was asked for.

    The caveat is a note about a request the driver ignored. On an off row there
    is no request, and a row that always carries the parenthetical stops reading
    it as a warning at all.
    """
    game = _game()
    game.settings = game.settings.with_video(vsync=False)
    scene = VideoScene(game)
    monkeypatch.setattr(VideoScene, "_vsync_is_active", staticmethod(lambda: False))

    label = scene._vsync_label()

    assert label.startswith("off")
    assert "not honoured" not in label, f"but there was no request to ignore: {label!r}"


def test_whole_pixel_art_says_when_there_is_nothing_to_snap() -> None:
    """A window already sized to a whole multiple honours the setting by doing nothing.

    The picture is right either way -- there was nothing to snap to -- but a row
    whose label flips while the screen sits still is indistinguishable from a
    dead one, which is the report this fixes. ``1152x648`` is the framing and so
    exactly one multiple of it.
    """
    game = _game()
    game.settings = game.settings.with_video(pixel_perfect=True)
    game.presentation.window_size = (1152, 648)
    game.stage = SimpleNamespace(size=(1152, 648))
    scene = VideoScene(game)

    item = scene.model.items[_row(scene, "pixel_perfect")]

    assert item.enabled, "the row is usable; it just has nothing to do"
    assert "already whole" in item.value, f"and says so: {item.value!r}"


def test_whole_pixel_art_still_plainly_reports_on_when_there_is_work_to_do() -> None:
    """The new caveat must not swallow the ordinary case.

    ``1152x648`` fits a whole multiple and is one; ``2304x1296`` is two. Neither
    is a multiple, so both rows should read a plain on and the picture should
    move -- and if the caveat were computed wrongly, this is the row that would
    start claiming there was nothing to do when there plainly was.
    """
    for window in ((1920, 1080), (2560, 1440)):
        game = _game()
        game.settings = game.settings.with_video(pixel_perfect=True)
        game.presentation.window_size = window
        game.stage = SimpleNamespace(size=window)
        scene = VideoScene(game)

        item = scene.model.items[_row(scene, "pixel_perfect")]

        assert item.value.startswith("on"), f"{window}: {item.value!r}"
        assert "already whole" not in item.value, f"{window} has work to do: {item.value!r}"


# --- the debug-only row -----------------------------------------------------


def test_the_panel_scale_row_is_absent_without_the_overlay() -> None:
    """Nothing to size when there are no panels.

    The first row in this screen's history to be conditional on anything, and
    gated on ``Debug.is_enabled()`` because ``--debug`` is nothing but the
    environment variable -- so that is the only thing that can say whether the
    overlay is on at the time this menu is built.
    """
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.delenv("DEBUG", raising=False)
    try:
        actions = [item.action for item in _drawn().model.items]
    finally:
        monkeypatch.undo()

    assert "panel_scale" not in actions
    assert actions == [
        "display",
        "pixel_perfect",
        "vsync",
        "frame_limit",
        "scale",
        "reset",
        "back",
        "info",
    ]


def test_the_panel_scale_row_appears_with_the_overlay() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DEBUG", "1")
    try:
        scene = _drawn()
        actions = [item.action for item in scene.model.items]
    finally:
        monkeypatch.undo()

    assert "panel_scale" in actions
    # Between the two size rows, so the scales read as one group.
    assert actions.index("panel_scale") == actions.index("scale") + 1


def test_the_row_reports_the_scale_it_will_apply() -> None:
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DEBUG", "1")
    try:
        scene = _drawn()
        index = _row(scene, "panel_scale")
    finally:
        monkeypatch.undo()

    assert scene.model.items[index].value == "1x"


def test_stepping_the_row_walks_the_panel_ladder_not_the_interface_one() -> None:
    """Its own ladder, because the interface one does not go low enough.

    ``UI_SCALES`` bottoms out at 0.8. The panels start from ``Debug.FONT_SIZE =
    24`` over a design frame, and at 1.0 only one of the five placeable panels
    finds a slot on a 640x480 window, so a ladder that starts at 0.8 would not
    offer a value that helps.
    """
    from src.application.settings_store import PANEL_SCALES

    assert min(PANEL_SCALES) == 0.4
    assert min(PANEL_SCALES) < 0.8

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DEBUG", "1")
    try:
        scene = _drawn()
        # Focused first: a direction key acts on the *selected* row, and the
        # selection starts on ``display``. Without this the press walked the
        # display mode and the panel scale never moved.
        _focus(scene, _row(scene, "panel_scale"))
        seen = []
        for _ in range(len(PANEL_SCALES)):
            seen.append(scene.game.settings.panel_scale)
            _press(scene, InputAction.UI_RIGHT)
    finally:
        monkeypatch.undo()

    assert seen == list(PANEL_SCALES[4:]) + list(PANEL_SCALES[:4]), seen
