from types import SimpleNamespace

import pygame

from src.application.scenes.controls_scene import ControlsScene
from src.application.scenes.resolution_scene import RESOLUTIONS, ResolutionScene
from src.application.scenes.video_scene import VideoScene
from src.application.settings_store import UserSettings
from src.core.input.event_router import EventRouter, InputDevice, RoutedInput
from src.core.input.input_actions import InputAction


def _game() -> SimpleNamespace:
    game = SimpleNamespace(
        settings=UserSettings(),
        scene_manager=SimpleNamespace(push=lambda _: None, pop=lambda: None),
    )
    game.input_router = EventRouter(game.settings.bindings)
    game.apply_bindings = lambda bindings: setattr(
        game, "settings", game.settings.with_bindings(bindings)
    )
    game.apply_settings = lambda settings: setattr(game, "settings", settings)
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
    assert row.keyboard is not None
    assert row.keyboard.text == "inverted"
    assert row.rebindable is False, "it is a toggle, not a remappable slot"

    controls.handle_routed(_confirm())

    assert game.settings.bindings.menu.invert_y is False


def test_gameplay_controls_do_not_expose_the_menu_stick_y() -> None:
    """The inversion applies to menus only; gameplay keeps its own rows."""
    controls = ControlsScene(_game(), ControlsScene.GAMEPLAY_SECTION)

    assert all(row.label != "Invert stick Y" for row in controls.rows)
    assert all(item.action != "invert_y" for item in controls.model.items)


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


def test_video_menu_cycles_presets_and_resets_video() -> None:
    game = _game()
    scene = VideoScene(game)
    initial = (game.settings.width, game.settings.height)
    assert initial in RESOLUTIONS

    # Arrows nudge the value inline; Enter opens the dedicated picker instead.
    scene.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))
    initial_index = RESOLUTIONS.index(initial)
    expected = RESOLUTIONS[(initial_index + 1) % len(RESOLUTIONS)]
    assert (game.settings.width, game.settings.height) == expected
    scene.handle_routed(RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD))
    assert (game.settings.width, game.settings.height) == initial

    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD))
    scene.handle_routed(_confirm())
    assert game.settings.fullscreen is True

    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD))
    scene.handle_routed(_confirm())
    assert game.settings.vsync is True

    _move_to_video(scene, "reset")
    scene.handle_routed(_confirm())
    defaults = UserSettings()
    assert (game.settings.width, game.settings.height) == (
        defaults.width,
        defaults.height,
    )
    assert game.settings.fullscreen is defaults.fullscreen
    assert game.settings.vsync is defaults.vsync
    assert game.settings.ui_scale == defaults.ui_scale


def _move_to_video(scene: VideoScene, action: str) -> None:
    """Select the row carrying ``action`` (the menu does not wrap)."""
    index = next(
        (i for i, item in enumerate(scene.model.items) if item.action == action),
        None,
    )
    assert index is not None, f"row {action!r} does not exist"
    scene.model.set_items(scene.model.items, index)


def test_video_menu_cycles_the_ui_scale() -> None:
    """UI scale moved here from the Options hub; it cycles like the presets."""
    game = _game()
    scene = VideoScene(game)
    _move_to_video(scene, "scale")

    scene.handle_routed(_confirm())
    assert game.settings.ui_scale == 1.2
    scene.handle_routed(RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD))
    assert game.settings.ui_scale == 1.0
    scene.handle_routed(RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD))
    assert game.settings.ui_scale == 0.8


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
    scene.handle_routed(_confirm())
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
    assert cell.rebindable is False

    controls.handle_routed(
        RoutedInput(InputAction.UI_POINTER_DOWN, InputDevice.MOUSE, position=cell.rect.center)
    )

    assert controls.capturing is False
    assert game.settings.bindings.menu.invert_y is True


def test_video_opens_a_resolution_picker_instead_of_only_cycling() -> None:
    """Enter on the Resolution row opens the list; ←/→ keep the quick nudge."""
    pushed: list[object] = []
    game = _game()
    game.scene_manager.push = pushed.append
    scene = VideoScene(game)

    _move_to_video(scene, "resolution")
    scene.handle_routed(_confirm())

    assert len(pushed) == 1
    assert isinstance(pushed[0], ResolutionScene)
    assert (game.settings.width, game.settings.height) == (
        UserSettings().width,
        UserSettings().height,
    ), "opening the list must not change the size yet"

    scene = VideoScene(game)
    _move_to_video(scene, "resolution")
    pushed.clear()
    scene.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))

    assert pushed == [], "arrows still nudge inline, no screen pushed"
    assert game.settings.width != UserSettings().width


def test_resolution_picker_lists_every_preset_and_marks_the_current_one() -> None:
    game = _game()
    scene = ResolutionScene(game)
    labels = [item.label for item in scene.model.items]

    assert len(labels) == len(RESOLUTIONS) + 1
    for width, height in RESOLUTIONS:
        assert any(label.startswith(f"{width} x {height}") for label in labels)
    current = [label for label in labels if label.endswith(ResolutionScene.CURRENT_SUFFIX)]
    assert current == [
        f"{UserSettings().width} x {UserSettings().height}" + ResolutionScene.CURRENT_SUFFIX
    ]
    assert scene.model.items[-1].action == "back"


def test_resolution_picker_preselects_the_active_resolution() -> None:
    game = _game()
    scene = ResolutionScene(game)

    current = (game.settings.width, game.settings.height)
    index = list(RESOLUTIONS).index(current)

    assert scene.model.current_index == index


def test_resolution_picker_applies_the_picked_size_and_returns() -> None:
    pops: list[str] = []
    applied: list[tuple[int, int]] = []
    game = _game()
    game.scene_manager.pop = lambda: pops.append("pop")
    scene = ResolutionScene(game)
    target = next(
        size for size in RESOLUTIONS if size != (game.settings.width, game.settings.height)
    )

    def apply_settings(settings: UserSettings) -> None:
        game.settings = settings
        applied.append((settings.width, settings.height))

    game.apply_settings = apply_settings
    scene.model.set_items(scene.model.items, RESOLUTIONS.index(target))
    scene.handle_routed(_confirm())

    assert applied == [target]
    assert (game.settings.width, game.settings.height) == target
    assert pops == ["pop"], "picking a size falls back to the Video menu"


def test_resolution_picker_back_and_escape_return_without_applying() -> None:
    pops: list[str] = []
    game = _game()
    game.scene_manager.pop = lambda: pops.append("pop")
    before = (game.settings.width, game.settings.height)
    scene = ResolutionScene(game)
    scene.model.set_items(scene.model.items, len(RESOLUTIONS))
    scene.handle_routed(_confirm())

    scene = ResolutionScene(game)
    scene.handle_routed(RoutedInput(InputAction.UI_BACK, InputDevice.KEYBOARD))

    assert pops == ["pop", "pop"]
    assert (game.settings.width, game.settings.height) == before


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


def test_resolution_picker_selection_survives_a_redraw() -> None:
    """Regression: the cursor used to snap back to the current size every frame.

    ``draw`` rebuilt the list to refresh the ``(current)`` marker, and
    ``set_items`` re-selects the current resolution, so walking down the list
    was impossible: the next frame undid the move. The list must only be
    rebuilt when the applied size actually changes.
    """
    pygame.font.init()
    game = _game()
    pygame.display.set_mode((1440, 900))
    scene = ResolutionScene(game)
    start = scene.model.current_index

    seen: list[int] = []
    for _ in range(3):
        scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
        scene.draw()  # the frame that runs right after the input
        seen.append(scene.model.current_index)

    assert seen == [start + 1, start + 2, start + 3]
    assert scene.model.current_index == start + 3
    assert scene.model.current_item is not None
    assert scene.model.current_item.action.startswith("res:")


def test_resolution_picker_refreshes_the_marker_when_the_size_changes() -> None:
    """The ``(current)`` marker still follows an externally applied size."""
    from dataclasses import replace as dataclass_replace

    game = _game()
    pygame.display.set_mode((1440, 900))
    scene = ResolutionScene(game)
    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    moved_to = scene.model.current_item.action
    assert moved_to is not None

    game.settings = dataclass_replace(game.settings, width=1920, height=1080)
    scene.draw()

    current = [
        item.label
        for item in scene.model.items
        if item.label.endswith(ResolutionScene.CURRENT_SUFFIX)
    ]
    assert current == ["1920 x 1080" + ResolutionScene.CURRENT_SUFFIX]
    assert scene.model.current_item is not None
    assert scene.model.current_item.action == moved_to, "the cursor must not jump on refresh"
