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

from src.application.scenes.option_screen import OptionScreen
from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import PANEL_SCALES, UserSettings
from src.core.display.letterbox import FitPolicy
from src.core.display.mode import DisplayMode
from src.core.display.monitors import Monitor, Topology
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
#: Whole-pixel art is not a row any more. It is the integer entry inside the fit
#: list, because it is that same setting and having both was a row that changed
#: its label and changed nothing on screen.
BOOLEAN_ROWS = frozenset({"vsync"})
LIST_ROWS = frozenset(VideoScene.SUBMENUS)

#: A window with room for a whole multiple of the framing, so every row that can
#: be enabled is. The read-out row needs one to report at all.
WINDOW = (2304, 1296)

#: The machine this screen is being tested on: three displays, the second of them
#: at a negative origin because a Linux desktop whose primary is not leftmost
#: puts the left monitor there.
#:
#: Fixed rather than read from the platform, because the rows under test are
#: conditional on the *number* of displays -- the screen picker only exists on a
#: multi-screen desk -- and a suite that skipped it whenever CI happened to be
#: headless would never check the one row that can put the window on the wrong
#: monitor. Names are the real EDID shape, including a duplicate pair, so the
#: label disambiguation is exercised too.
DESK = Topology(
    monitors=(
        Monitor(0, 'DP-1 27"', (0, 0, 2560, 1440), (0, 0, 2560, 1400), 180),
        Monitor(1, 'DP-2 27"', (-1920, -120, 1920, 1080), (-1920, -120, 1920, 1040), 60),
        Monitor(2, 'HDMI-1 27"', (-1920, -120, 1920, 1080), (-1920, -120, 1920, 1040), 144),
    ),
    named=True,
)


def _game(
    display: DisplayMode = DisplayMode.WINDOW, topology: Topology | None = None
) -> SimpleNamespace:
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
        topology=lambda: topology or DESK,
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


def _drawn(display: DisplayMode = DisplayMode.WINDOW, topology: Topology | None = None):
    """A scene whose view has laid out, so its row rectangles exist."""
    pygame.init()
    scene = VideoScene(_game(display, topology))
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


#: The display mode each row needs to be *enabled*. A row that cannot be used is
#: skipped by the focus walk -- deliberately, so a disabled row swallows a press
#: instead of activating whatever is nearest -- which means a test that wants to
#: press a row has to build the screen where that row is live.
DISPLAY_FOR_ROW = {"fullscreen_mode": DisplayMode.FULLSCREEN}


def _scene_for(action: str) -> VideoScene:
    """A drawn scene in which ``action``'s row can be pressed."""
    return _drawn(DISPLAY_FOR_ROW.get(action, DisplayMode.WINDOW))


def _list_for(scene: VideoScene, row: str) -> OptionScreen:
    """Open ``row``'s list and return the pushed screen.

    Through the real ``_open``, so the test exercises the same push the player's
    press does rather than a hand-built screen that could differ from it.
    """
    pushed: list[object] = []
    scene.game.scene_manager.push = pushed.append
    assert _focus_action(scene, row), f"the {row!r} row was not reachable"
    scene._open(row)
    assert len(pushed) == 1, f"the {row!r} row opened {len(pushed)} lists"
    screen = pushed[0]
    assert isinstance(screen, OptionScreen)
    return screen


def _focus_action(scene: VideoScene, action: str) -> bool:
    """Put the focus on ``action``, pressing down until it arrives or runs out.

    Returns whether it got there. The failure case is reported by the caller
    rather than raised here, because "this row could not be reached" is an
    ordinary outcome for a test that is about something else -- and a helper that
    raises turns it into an error about the wrong thing.
    """
    for _ in range(len(scene.model.items) + 2):
        current = scene.model.current_item
        if current is not None and current.action == action:
            return True
        scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    return False


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    pygame.init()
    if not pygame.display.get_surface():
        pygame.display.set_mode((320, 240))


@pytest.mark.parametrize("action", VideoScene.CYCLING_ROWS)
def test_a_click_steps_the_row(action: str) -> None:
    scene = _scene_for(action)
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
    by_click = _scene_for(action)
    _click(by_click, _row(by_click, action))

    by_key = _scene_for(action)
    _focus_action(by_key, action)
    by_key.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.KEYBOARD))

    assert by_click.game.settings == by_key.game.settings


def test_every_row_does_something() -> None:
    """No row may be outside all three lists.

    This is the check that names the bug: the rows were split between one that
    a click reached and one that a key reached, and a row in neither is
    invisible until someone tries it. There are now three ways a row can act --
    cycle a value, open a list, or be one of the named actions -- and a row has to
    be in one of them.
    """
    scene = _drawn()
    reachable = set(VideoScene.CYCLING_ROWS) | set(VideoScene.SUBMENUS) | ACTION_ROWS | REPORT_ROWS

    assert {item.action for item in scene.model.items} <= reachable
    # And the sets are disjoint, so a row cannot be quietly claimed by two of
    # them and left to whichever runs first.
    assert not set(VideoScene.CYCLING_ROWS) & set(VideoScene.SUBMENUS)
    assert not set(VideoScene.CYCLING_ROWS) & ACTION_ROWS
    assert not REPORT_ROWS & (set(VideoScene.CYCLING_ROWS) | set(VideoScene.SUBMENUS) | ACTION_ROWS)
    for item in scene.model.items:
        if item.action in REPORT_ROWS:
            assert not item.enabled, "a read-out row must not be actionable"


def test_every_list_row_really_has_a_list() -> None:
    """Every row that claims to open a list does, and the names agree.

    Two tables have to agree: the rows the screen offers and the builders that
    fill them. A row in the first and not the second is a row that swallows
    every press, which is exactly the dead-row failure this file has produced
    twice -- and it is invisible until someone tries it on that row.
    """
    for row in VideoScene.SUBMENUS:
        assert hasattr(VideoScene, f"_submenu_{row}"), f"the {row!r} row has no builder"


@pytest.mark.parametrize("row", sorted(set(VideoScene.SUBMENUS)))
def test_a_list_row_opens_its_list_from_a_click_and_from_every_key(row: str) -> None:
    """All three ways into the list reach it, and open the same one.

    A list row that answered a click but not → is a row that looks alive and does
    nothing -- the failure mode from §10 of the notes, where six of nine rows
    highlighted on click and changed nothing.
    """
    pushed: list[object] = []

    for press in ("click", "right", "confirm"):
        scene = _scene_for(row)
        scene.game.scene_manager.push = pushed.append
        if press == "click":
            _click(scene, _row(scene, row))
        else:
            _focus_action(scene, row)
            scene.handle_routed(
                RoutedInput(
                    InputAction.UI_CONFIRM if press == "confirm" else InputAction.UI_RIGHT,
                    InputDevice.KEYBOARD,
                )
            )
        assert pushed, f"{press!r} on the {row!r} row opened nothing"

    # The three presses build three separate screens -- each press goes through
    # the real push, so a shared object would mean the second press reused the
    # first one's list rather than rebuilding it. What has to match is their
    # content: three different lists here would be three different bugs.
    lists = [(screen.title, tuple(o.label for o in screen.options)) for screen in pushed]
    assert len(set(lists)) == 1, f"the three paths opened different lists: {lists}"


def test_highlighting_a_list_entry_does_not_apply_it() -> None:
    """Apply on selection, not on highlight.

    The alternative looks better and is a trap: browsing a 28-entry list would
    rebuild the window on every row the highlight touched, and a player who
    scrolled past something would leave the game in it. Highlight is a cursor,
    selection is a choice, and only the second one is something the player did.
    """
    scene = _drawn()
    pushed: list[object] = []
    scene.game.scene_manager.push = pushed.append
    _focus_action(scene, "frame_limit")
    before = scene.game.settings.frame_limit

    screen = _list_for(scene, "frame_limit")
    for _ in range(4):
        screen.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))

    assert screen.model.current_index != 0, "the fixture did not move the cursor"
    assert scene.game.settings.frame_limit == before, "browsing changed a setting"


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


def test_the_whole_pixel_setting_is_an_entry_in_the_fit_list_not_a_row() -> None:
    """The contradiction that made the row dead is gone, not relabelled.

    Whole-pixel art and the integer fit policy were the same setting, on two
    different rows. With zoom chosen, the whole-pixel row flipped its label and
    changed the stored flag while the picture stayed byte-identical -- a row that
    responds to every key and does nothing, which is indistinguishable from a
    broken key.

    So there is no longer a row, and the one thing it did is an entry in the fit
    list where the sentence explaining what whole-pixel art is has room to be
    read. What replaces the row is the thing that must hold: whatever the fit
    policy, the flag agrees with it, so there is no second control to contradict.
    """
    scene = _drawn()
    assert "pixel_perfect" not in {item.action for item in scene.model.items}

    screen = _list_for(scene, "fit")
    labels = {option.label: option for option in screen.options}
    assert "integer" in labels, "the whole-pixel choice has to live somewhere"
    assert labels["integer"].detail, "and it has to explain itself"


@pytest.mark.parametrize("policy", list(FitPolicy))
def test_the_whole_pixel_flag_always_agrees_with_the_fit_policy(policy: FitPolicy) -> None:
    """The invariant that replaces the dead row.

    Whatever the player picks, the stored flag is written from it rather than
    left over from before. That is what stops a v3 file's ``pixel_perfect`` from
    overriding a later choice on the next launch -- which is the bug that made
    the row look broken to a player and pass every test written with the
    arrow keys.
    """
    scene = _drawn()
    screen = _list_for(scene, "fit")
    wanted = f"option:{next(i for i, o in enumerate(screen.options) if o.value is policy)}"
    assert _focus_action(screen, wanted), f"{policy.value} was not reachable in the fit list"
    screen.handle_routed(RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD))

    assert scene.game.settings.fit is policy
    assert scene.game.settings.pixel_perfect is (policy is FitPolicy.INTEGER)


def test_the_fit_list_says_so_on_a_window_too_small_for_whole_pixel() -> None:
    """The one refusal the fit policy has, said in the list where it is chosen.

    A window narrower than the framing has no whole multiple to snap to, so
    ``integer`` cannot do anything here. The entry says so, rather than accepting
    a choice that will look like it worked -- the same refusal the row used to
    make, moved to where the decision is now taken.
    """
    game = _game()
    game.presentation.window_size = (800, 600)
    game.stage = SimpleNamespace(size=(800, 600))
    scene = VideoScene(game)
    scene.draw(pygame.Surface((1152, 648)))

    screen = _list_for(scene, "fit")
    integer = next(option for option in screen.options if option.value is FitPolicy.INTEGER)
    assert "too small" in integer.detail


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
        return _scene_for(action).game.settings
    start_on = key is InputAction.UI_LEFT
    return _scene_for(action).game.settings.with_video(**{action: start_on})


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
    scene = _scene_for(action)
    scene.game.settings = _starting_settings(action, key)
    _focus_action(scene, action)
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
    scene = _scene_for(action)

    _focus_action(scene, action)
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
    _focus_action(on, action)
    _press(on, InputAction.UI_LEFT)

    off = _drawn()
    _focus_action(off, action)
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
    by_confirm = _scene_for(action)
    _focus_action(by_confirm, action)
    _press(by_confirm, InputAction.UI_CONFIRM)

    by_right = _scene_for(action)
    _focus_action(by_right, action)
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
        "monitor",
        "fullscreen_mode",
        "fit",
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
