from types import SimpleNamespace

import pygame

from src.application.scenes.controls_scene import ControlsScene
from src.application.scenes.option_screen import OptionScreen
from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import FRAME_LIMITS, UserSettings
from src.core.display.letterbox import FitPolicy
from src.core.display.monitors import degraded
from src.core.input.event_router import EventRouter, InputDevice, RoutedInput
from src.core.input.input_actions import InputAction
from src.ui.controls_view import RowKind


def _game() -> SimpleNamespace:
    game = SimpleNamespace(
        settings=UserSettings(),
        scene_manager=SimpleNamespace(push=lambda _: None, pop=lambda: None),
        # The video screen reports the window it is in, so a stand-in has to
        # have one. A 16:9 window with room for a whole multiple of the framing,
        # which is the case where every row is usable.
        presentation=SimpleNamespace(
            stage=pygame.Surface((2304, 1296)),
            pixel_perfect=False,
            window_size=(2304, 1296),
            density=2.0,
        ),
        stage=None,
        # The video screen asks the runtime what displays exist, so a stand-in
        # has to answer. One screen with no names: enough for the rows that are
        # about pacing and scaling, and it keeps the screen-picker row out of a
        # screen-picker-agnostic test.
        topology=lambda: degraded(((2304, 1296),)),
        # The screen the window is on, which is what the VSync row reports: the
        # primary's rate would be a claim about a screen the window may not be on.
        window_monitor=lambda: degraded(((2304, 1296),)).primary,
        # The views are laid out at the preference times the density; a stand-in
        # has to hand them something, and 1.0 keeps the assertions readable.
        ui_scale=1.0,
    )
    game.input_router = EventRouter(game.settings.bindings)

    def _apply(settings):
        game.settings = settings
        game.ui_scale = settings.ui_scale

    game.apply_bindings = lambda bindings: _apply(game.settings.with_bindings(bindings))
    game.apply_settings = _apply
    return game


def _confirm() -> RoutedInput:
    return RoutedInput(InputAction.UI_CONFIRM, InputDevice.KEYBOARD)


def test_controls_exposes_keyboard_and_gamepad_columns() -> None:
    controls = ControlsScene(_game(), ControlsScene.MENU_SECTION)

    assert [row.label for row in controls.rows[:4]] == [
        "Move up",
        "Move down",
        "Move left",
        "Move right",
    ]
    assert controls.rows[0].keyboard is not None
    assert controls.rows[0].gamepad is not None
    assert controls.view.COLUMN_HEADERS == ("KEYBOARD / MOUSE", "GAMEPAD")


def test_gamepad_button_capture_is_independent_from_keyboard() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.GAMEPLAY_SECTION)
    controls.model.set_items(controls.model.items, 3)  # Jump
    controls.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=7))

    assert game.settings.bindings.gameplay.gamepad_buttons[InputAction.JUMP] == 7
    assert game.settings.bindings.gameplay.keyboard[InputAction.JUMP] == pygame.K_SPACE


def test_gameplay_left_and_right_are_separate_rows_and_captures() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.GAMEPLAY_SECTION)

    assert [row.label for row in controls.rows[:2]] == ["Move left", "Move right"]

    controls.model.set_items(controls.model.items, 0)
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a))
    controls.model.set_items(controls.model.items, 1)
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))

    assert game.settings.bindings.gameplay.keyboard[InputAction.MOVE_X] == (
        pygame.K_a,
        pygame.K_d,
    )


def test_gamepad_dpad_left_and_right_capture_updates_only_their_half() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.GAMEPLAY_SECTION)
    controls.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))
    controls.model.set_items(controls.model.items, 0)
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=8))
    controls.model.set_items(controls.model.items, 1)
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=9))

    assert game.settings.bindings.gameplay.gamepad_buttons[InputAction.MOVE_X] == (8, 9)

    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    controls.model.set_items(controls.model.items, 6)  # Cancel
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2))

    assert game.settings.bindings.menu.mouse_buttons[InputAction.UI_CANCEL] == 2
    assert game.settings.bindings.menu.keyboard[InputAction.UI_CANCEL] == pygame.K_q


def test_gamepad_axis_capture_updates_both_vertical_directions() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    controls.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.JOYAXISMOTION, axis=3, value=1.0))

    assert game.settings.bindings.menu.gamepad_axes[InputAction.UI_UP] == 3
    assert game.settings.bindings.menu.gamepad_axes[InputAction.UI_DOWN] == 3


def _move_to(scene: ControlsScene, action: str) -> None:
    """Select the row carrying ``action``.

    The menu deliberately does not wrap, so walking with ↑↓ cannot revisit a
    row above the current one. Selecting by action (through the model index)
    keeps these tests honest when a row is inserted, e.g. the invert-Y toggle.
    """
    index = next(
        (i for i, item in enumerate(scene.model.items) if item.action == action),
        None,
    )
    assert index is not None, f"row {action!r} does not exist"
    scene.model.set_items(scene.model.items, index)


def test_controls_reset_restores_only_selected_section() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    original_gameplay = game.settings.bindings.gameplay
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x))
    assert game.settings.bindings.menu.keyboard[InputAction.UI_UP] == pygame.K_x

    _move_to(controls, "reset")
    controls.handle_routed(_confirm())

    assert game.settings.bindings.menu == UserSettings().bindings.menu
    assert game.settings.bindings.gameplay == original_gameplay


def test_controls_reset_and_back_are_real_navigation_rows() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)

    _move_to(controls, "reset")
    assert controls.model.current_item is not None
    assert controls.model.current_item.action == "reset"
    reset_index = controls.model.current_index
    assert controls.rows[reset_index].label == "Reset to defaults"

    controls.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    assert controls.model.current_item is not None
    assert controls.model.current_item.action == "back"
    assert controls.rows[controls.model.current_index].label == "Back"


def test_menu_controls_expose_the_stick_y_inversion() -> None:
    """The invert-Y toggle lives with the menu bindings, not in Video."""
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    labels = [row.label for row in controls.rows]
    assert "Invert stick Y" in labels
    assert labels.index("Invert stick Y") < labels.index("Reset to defaults")

    _move_to(controls, "invert_y")
    controls.handle_routed(_confirm())

    assert game.settings.bindings.menu.invert_y is True
    row = next(row for row in controls.rows if row.label == "Invert stick Y")
    # The state is printed under GAMEPAD, because that is the device it applies
    # to: a state under KEYBOARD / MOUSE reads as a key bound to a switch.
    assert row.keyboard is None
    assert row.gamepad is not None
    assert row.gamepad.text == "inverted"
    assert row.rebindable is False, "it is a toggle, not a remappable slot"

    controls.handle_routed(_confirm())

    assert game.settings.bindings.menu.invert_y is False


def test_gameplay_controls_do_not_expose_the_menu_stick_y() -> None:
    """The inversion applies to menus only; gameplay keeps its own rows."""
    controls = ControlsScene(_game(), ControlsScene.GAMEPLAY_SECTION)

    assert all(row.label != "Invert stick Y" for row in controls.rows)
    assert all(item.action != "invert_y" for item in controls.model.items)


def test_the_options_at_the_bottom_are_options_and_not_binding_slots() -> None:
    """Both controls screens end on a block of choices, not on slots to fill.

    The rows above are keys to assign; the ones below are things to pick --
    invert the Y axis, reset, go back. They were painted as binding rows, with
    a key in each column ("Esc / right click", "B / right click"), which is the
    one thing that cannot be true of them: there is no key to press on "Reset to
    defaults". A player counts them among the assignments and looks for one.

    So they are ``OPTION`` rows, which the panel sets apart with a gap and greys,
    and they carry no key at all. The toggle keeps its state, in the column of
    the device it applies to.
    """
    for section in (ControlsScene.MENU_SECTION, ControlsScene.GAMEPLAY_SECTION):
        rows = ControlsScene(_game(), section).rows
        kinds = [row.kind for row in rows]
        options = [index for index, kind in enumerate(kinds) if kind is RowKind.OPTION]

        assert options, f"{section} has no option row"
        assert options == list(range(options[0], len(rows))), (
            f"{section}: the options are not the block at the bottom: {[row.label for row in rows]}"
        )
        for row in rows[options[0] :]:
            assert row.rebindable is False
            assert row.keyboard is None, f"{row.label} shows a keyboard key"
        for row in rows[: options[0]]:
            assert row.kind is RowKind.REBIND
            assert row.keyboard is not None and row.gamepad is not None, row.label

    # The toggle is the one option with a value, and it is the stick's.
    menu_rows = ControlsScene(_game(), ControlsScene.MENU_SECTION).rows
    toggle = next(row for row in menu_rows if row.label == "Invert stick Y")
    assert toggle.gamepad is not None and toggle.gamepad.text == "normal"


def test_controls_focus_is_rendered_on_the_footer_rows() -> None:
    """Invert Y, Reset and Back are all selectable, so all get a focus ring."""
    pygame.font.init()
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    surface = pygame.Surface((1024, 720))
    calls: list[tuple[int, int, int, int, int]] = []
    original_rect = pygame.draw.rect

    def record_rect(target, color, rect, width=0):
        calls.append((*rect, width))
        return original_rect(target, color, rect, width)

    _move_to(controls, "reset")
    reset_index = controls.model.current_index
    _move_to(controls, "invert_y")
    invert_index = controls.model.current_index
    back_index = controls.model.current_index + 1

    pygame.draw.rect = record_rect
    try:
        for selected in (invert_index, reset_index, back_index):
            before = len(calls)
            controls.view.draw(
                surface,
                "MENU CONTROLS",
                "Keyboard / mouse",
                controls.rows,
                selected_row=selected,
                selected_column=0,
                top=80,
            )
            assert any(width == 1 for *_, width in calls[before:]), selected
    finally:
        pygame.draw.rect = original_rect


def test_video_menu_cycles_every_value_row_and_resets() -> None:
    """Every row acts on left/right/confirm, so a gamepad never lands on a
    row it cannot use."""
    game = _game()
    scene = VideoScene(game)

    def row(name: str):
        return next(i for i, item in enumerate(scene.model.items) if item.action == name)

    def focus(name: str) -> None:
        # Walk to the top, then down. A press can skip a row -- the model steps
        # over disabled ones, which is the whole point of them -- so this counts
        # positions rather than assuming one press per row.
        for _ in range(len(scene.model.items)):
            scene.handle_routed(RoutedInput(InputAction.UI_UP, InputDevice.GAMEPAD))
            if scene.model.current_index == 0:
                break
        for _ in range(len(scene.model.items)):
            if scene.model.current_index >= row(name):
                break
            scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD))
        assert scene.model.current_index == row(name)

    # The window size is a list, and the row that owns it has to be reachable by
    # the same walk every other row is: the display row this replaced is gone,
    # and nothing may go with it. The list's own contents are checked in the
    # video-screen tests; what this pins is that the row is live and opens.
    focus("size")
    size_list = _open_list(scene, "size")
    assert size_list.options, "the window-size row opened an empty list"

    # A press sets the value rather than toggling it: left is off, right is on,
    # so the two directions cannot behave identically.
    focus("vsync")
    scene.handle_routed(RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD))
    assert game.settings.vsync is False
    scene.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))
    assert game.settings.vsync is True

    # Frame limit is a list now, and it opens on a gamepad press like anything
    # else. Every value has to be reachable *through the list*, which is the
    # point: a list the gamepad cannot walk is a list only a mouse can use.
    limits: set[object] = set()
    for _ in range(len(FRAME_LIMITS)):
        limits.add(game.settings.frame_limit)
        list_screen = _open_list(scene, "frame_limit")
        for option in list_screen.options:
            _focus_option(list_screen, f"option:{list_screen.options.index(option)}")
            list_screen.handle_routed(_confirm())
            limits.add(game.settings.frame_limit)
    assert limits == set(FRAME_LIMITS), "every frame limit must be reachable"

    focus("scale")
    before = game.settings.ui_scale
    scale_list = _open_list(scene, "scale")
    _focus_option(scale_list, "option:2")
    scale_list.handle_routed(_confirm())
    assert game.settings.ui_scale != before

    _move_to_video(scene, "reset")
    scene.handle_routed(_confirm())
    defaults = UserSettings()
    assert game.settings.pixel_perfect == defaults.pixel_perfect
    assert game.settings.frame_limit == defaults.frame_limit
    assert game.settings.ui_scale == defaults.ui_scale


def test_the_fit_list_says_so_on_a_window_too_small_for_whole_pixel() -> None:
    """The one refusal the fit policy has, said where the choice is made.

    Whole-pixel art needs a whole multiple of the framing to snap to, and a
    window narrower than the framing has none. The entry says so rather than
    silently accepting a choice that does nothing -- which is what an entry
    reading "integer" on a window it cannot honour would be.

    It lives in the fit list now rather than on its own row, because it is the
    same setting as the integer policy and two rows for one setting is how the
    dead row happened in the first place.
    """
    game = _game()
    game.presentation.window_size = (800, 600)
    game.presentation.stage = pygame.Surface((800, 600))
    scene = VideoScene(game)
    integer = next(
        option for option in _open_list(scene, "fit").options if option.value is FitPolicy.INTEGER
    )

    assert "too small" in integer.detail

    game.presentation.window_size = (2304, 1296)
    game.presentation.stage = pygame.Surface((2304, 1296))
    scene = VideoScene(game)
    integer = next(
        option for option in _open_list(scene, "fit").options if option.value is FitPolicy.INTEGER
    )
    assert "too small" not in integer.detail


def test_every_video_row_reports_its_value_in_its_own_column() -> None:
    """A settings screen is a table; the state belongs in a column."""
    scene = VideoScene(_game())

    for item in scene.model.items:
        if item.action in ("reset", "back"):
            assert item.value == ""
        else:
            assert item.value, f"{item.action} reports no value"


def _move_to_video(scene: VideoScene, action: str) -> None:
    """Select the row carrying ``action`` (the menu does not wrap)."""
    index = next(
        (i for i, item in enumerate(scene.model.items) if item.action == action),
        None,
    )
    assert index is not None, f"row {action!r} does not exist"
    scene.model.set_items(scene.model.items, index)


def _open_list(scene: VideoScene, row: str) -> OptionScreen:
    """Open ``row``'s list through the real push and return what came out.

    Through ``handle_routed`` rather than by calling ``_open`` directly, so the
    press that opens it is the one a player makes.
    """
    pushed: list[object] = []
    scene.game.scene_manager.push = pushed.append
    _move_to_video(scene, row)
    scene.handle_routed(_confirm())
    assert pushed, f"the {row!r} row opened nothing"
    screen = pushed[0]
    assert isinstance(screen, OptionScreen)
    return screen


def _focus_option(screen: OptionScreen, action: str) -> None:
    """Put a list's cursor on ``action``, walking up to the top first.

    From the top every time, because the list does not wrap: walking down from
    wherever the cursor happens to be cannot reach an entry above it, and a test
    that visited the options in order would pass while a player who scrolled down
    and then wanted to go back could not.
    """
    for _ in range(len(screen.model.items)):
        screen.handle_routed(RoutedInput(InputAction.UI_UP, InputDevice.KEYBOARD))
    for _ in range(len(screen.model.items) + 2):
        current = screen.model.current_item
        if current is not None and current.action == action:
            return
        screen.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    raise AssertionError(f"the list never reached {action!r}")


def test_video_menu_opens_the_ui_scale_list_and_it_applies_on_selection() -> None:
    """UI scale moved here from the Options hub; it is now a list, not a cycle.

    Three values would cycle acceptably, but a list is what every other setting
    of this size uses and it is where the consequence lives -- "text at 2.00x on
    this screen", which the old row could not say. Apply happens on the pick, not
    on the highlight, so browsing the list changes nothing.
    """
    game = _game()
    scene = VideoScene(game)
    _move_to_video(scene, "scale")

    list_screen = _open_list(scene, "scale")
    assert list_screen.title == "UI SCALE"
    # Opening it changed nothing.
    assert game.settings.ui_scale == 1.0

    _focus_option(list_screen, "option:2")
    list_screen.handle_routed(_confirm())
    assert game.settings.ui_scale == 1.2


def test_video_menu_keeps_the_focus_on_the_row_it_just_edited() -> None:
    """Editing a value must not jump the selection to another row."""
    game = _game()
    scene = VideoScene(game)
    _move_to_video(scene, "scale")

    scene.handle_routed(_confirm())

    assert scene.model.current_item is not None
    assert scene.model.current_item.action == "scale"


def test_video_reset_also_restores_the_ui_scale() -> None:
    game = _game()
    scene = VideoScene(game)
    _move_to_video(scene, "scale")
    list_screen = _open_list(scene, "scale")
    _focus_option(list_screen, "option:2")
    list_screen.handle_routed(_confirm())
    assert game.settings.ui_scale != UserSettings().ui_scale

    _move_to_video(scene, "reset")
    scene.handle_routed(_confirm())

    assert game.settings.ui_scale == UserSettings().ui_scale


def test_every_row_is_hoverable_including_non_rebindable_ones() -> None:
    """Hovering must move the focus on every row, not only the rebindable ones.

    Regression: the hit-test only registered cells of rebindable rows, so the
    invert-Y toggle, Reset and Back could never receive the pointer focus.
    """
    pygame.font.init()
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    surface = pygame.Surface((1440, 900))
    controls.view.draw(
        surface,
        "MENU CONTROLS",
        "Keyboard / mouse",
        controls.rows,
        selected_row=0,
        selected_column=0,
        top=80,
    )
    labels = [row.label for row in controls.rows]

    for index, label in enumerate(labels):
        rect = controls.view.row_rects[index]
        controls.model.set_items(controls.model.items, 0)

        controls.handle_routed(
            RoutedInput(InputAction.UI_POINTER_MOVE, InputDevice.MOUSE, position=rect.center)
        )

        assert controls.model.current_index == index, label
        assert controls.model.current_item is not None
        assert controls.model.current_item.action is not None


def test_hovering_a_non_rebindable_cell_does_not_open_a_capture() -> None:
    """A click on invert Y activates it; it must not start an empty capture."""
    pygame.font.init()
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    surface = pygame.Surface((1440, 900))
    controls.view.draw(
        surface,
        "MENU CONTROLS",
        "Keyboard / mouse",
        controls.rows,
        selected_row=0,
        selected_column=0,
        top=80,
    )
    index = [row.label for row in controls.rows].index("Invert stick Y")
    row_rect = controls.view.row_rects[index]
    cell = next(
        (
            candidate
            for x in range(row_rect.left, row_rect.right)
            if (candidate := controls.view.cell_at((x, row_rect.centery))) is not None
        ),
        None,
    )
    assert cell is not None, "the invert-Y row must expose a hoverable cell"
    assert cell.row == index
    assert cell.activatable is False

    controls.handle_routed(
        RoutedInput(InputAction.UI_POINTER_DOWN, InputDevice.MOUSE, position=cell.rect.center)
    )

    assert controls.capturing is False
    assert game.settings.bindings.menu.invert_y is True


def test_keyboard_capture_prompt_replaces_only_the_armed_cell() -> None:
    """Arming a capture must not paint the whole column with the prompt.

    Regression: both cell formatters matched the capture against
    ``model.current_index`` — the same value for every row — instead of the row
    being built, so arming one cell turned the entire keyboard column into
    “Press a key…”.
    """
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    _move_to(controls, "rebind_1")  # Move down
    controls.handle_routed(_confirm())

    keyboard = [row.keyboard.text for row in controls.rows if row.keyboard is not None]
    assert keyboard.count("Press a key…") == 1
    assert keyboard[1] == "Press a key…", "the prompt sits on the armed row only"
    assert keyboard[0] == "UP", "its neighbours keep their binding text"
    assert keyboard[2] == "LEFT"

    gamepad = [row.gamepad.text for row in controls.rows if row.gamepad is not None]
    assert "Press button / axis / d-pad…" not in gamepad, "the other column is untouched"


def test_gamepad_capture_prompt_replaces_only_the_armed_cell() -> None:
    """The gamepad column carried the same whole-column prompt bug."""
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    controls.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))
    controls.handle_routed(_confirm())

    gamepad = [row.gamepad.text for row in controls.rows if row.gamepad is not None]
    assert gamepad.count("Press button / axis / d-pad…") == 1
    assert gamepad[0] == "Press button / axis / d-pad…"
    assert gamepad[1] == "axis 1 / hat 0"

    keyboard = [row.keyboard.text for row in controls.rows if row.keyboard is not None]
    assert "Press a key…" not in keyboard


def test_the_window_row_only_reports_and_opens_nothing() -> None:
    """The read-out line is inert, and the rows that do open lists are the others.

    The window's size is a *choice* now and it lives on its own row with a list
    behind it; the read-out at the bottom is the opposite case -- a report of what
    the game derived from the window, which the player can change. It is drawn
    disabled on purpose: a report row that opened something would be reporting a
    choice it does not make.

    What this pins is that the report stays inert while the lists exist.
    """
    pushed: list[object] = []
    game = _game()
    game.scene_manager.push = pushed.append
    scene = VideoScene(game)
    before = game.settings

    report = next(item for item in scene.model.items if item.action == "info")
    assert not report.enabled
    assert "2304x1296" in report.value
    assert "2.00x" in report.value

    # The model refuses to put the selection on a disabled row, so the press
    # that would have opened something cannot be aimed at it in the first place:
    # the selection lands on the nearest row that is usable, which is the point.
    scene.model.set_items(scene.model.items, scene.model.items.index(report))
    assert scene.model.current_item is not report
    assert scene.model.current_item.enabled  # type: ignore[union-attr]

    # And the read-out owns no list at all -- a direct open is a no-op, not a
    # push that happens to be unreachable from the model.
    pushed.clear()
    scene._open("info")
    assert pushed == [], "the read-out row opened something"

    # Every other row that can be reached either cycles a value or opens a
    # list. The lists are the point of the check, not a violation of it: they
    # are built from what the driver and the topology report, so none of them
    # claims anything the game cannot check about the player's screen.
    for index, item in enumerate(scene.model.items):
        if not item.enabled:
            continue
        scene.model.set_items(scene.model.items, index)
        for action in (InputAction.UI_CONFIRM, InputAction.UI_RIGHT, InputAction.UI_LEFT):
            scene.handle_routed(RoutedInput(action, InputDevice.GAMEPAD))
        if item.action in ("reset",):
            game.settings = before

    for screen in pushed:
        assert isinstance(screen, OptionScreen), f"a row pushed a {type(screen).__name__}"
        assert all(option.enabled or option.label == "" for option in screen.options), (
            "a list offered an entry it could not apply without saying so"
        )


def test_one_stick_press_moves_exactly_one_row() -> None:
    """Regression: the release event must not add a second step.

    The router emits one extra routed input, carrying the held action, when the
    stick goes back to neutral. ``ControlsScene`` moves the cursor through
    ``MenuModel.move`` directly, so it used to skip two rows per press and felt
    unresponsive with a pad.
    """
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    router = EventRouter(game.settings.bindings)
    axis = game.settings.bindings.menu.gamepad_axes[InputAction.UI_DOWN]

    press = router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=axis, value=0.9)
    )
    assert press is not None and press.variant != "release"
    controls.handle_routed(press)
    after_press = controls.model.current_index

    release = router.route(
        pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=axis, value=0.0)
    )
    assert release is not None
    assert release.variant == "release"
    controls.handle_routed(release)

    assert after_press == 1
    assert controls.model.current_index == after_press, "release must not move the cursor"


def test_repeated_presses_walk_one_row_at_a_time() -> None:
    """Three full press/release cycles land on row 3, never further."""
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    router = EventRouter(game.settings.bindings)
    axis = game.settings.bindings.menu.gamepad_axes[InputAction.UI_DOWN]

    for _ in range(3):
        controls.handle_routed(
            router.route(
                pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=axis, value=0.9)
            )
        )
        controls.handle_routed(
            router.route(
                pygame.event.Event(pygame.JOYAXISMOTION, instance_id=0, axis=axis, value=0.0)
            )
        )

    assert controls.model.current_index == 3
