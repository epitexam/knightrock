from types import SimpleNamespace

import pygame

from src.application.scenes.controls_scene import ControlsScene
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


def test_controls_reset_restores_only_selected_section() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    original_gameplay = game.settings.bindings.gameplay
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x))
    assert game.settings.bindings.menu.keyboard[InputAction.UI_UP] == pygame.K_x

    controls.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    for _ in range(len(controls.specs) - controls.model.current_index):
        controls.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    controls.handle_routed(_confirm())

    assert game.settings.bindings.menu == UserSettings().bindings.menu
    assert game.settings.bindings.gameplay == original_gameplay


def test_controls_reset_and_back_are_real_navigation_rows() -> None:
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)

    for _ in range(len(controls.specs)):
        controls.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    assert controls.model.current_item is not None
    assert controls.model.current_item.action == "reset"
    assert controls.rows[len(controls.specs)].label == "Reset to defaults"

    controls.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.KEYBOARD))
    assert controls.model.current_item is not None
    assert controls.model.current_item.action == "back"
    assert controls.rows[len(controls.specs) + 1].label == "Back"


def test_controls_focus_is_rendered_on_reset_and_back_rows() -> None:
    pygame.font.init()
    game = _game()
    controls = ControlsScene(game, ControlsScene.MENU_SECTION)
    surface = pygame.Surface((1024, 720))
    calls: list[tuple[int, int, int, int, int]] = []
    original_rect = pygame.draw.rect

    def record_rect(target, color, rect, width=0):
        calls.append((*rect, width))
        return original_rect(target, color, rect, width)

    pygame.draw.rect = record_rect
    try:
        controls.view.draw(
            surface,
            "MENU CONTROLS",
            "Keyboard / mouse",
            controls.rows,
            selected_row=len(controls.specs),
            selected_column=0,
            top=80,
        )
        reset_calls = len(calls)
        controls.view.draw(
            surface,
            "MENU CONTROLS",
            "Keyboard / mouse",
            controls.rows,
            selected_row=len(controls.specs) + 1,
            selected_column=0,
            top=80,
        )
    finally:
        pygame.draw.rect = original_rect

    assert any(width == 1 for *_, width in calls[:reset_calls])
    assert any(width == 1 for *_, width in calls[reset_calls:])


def test_video_menu_cycles_presets_and_resets_video() -> None:
    game = _game()
    scene = VideoScene(game)
    initial = (game.settings.width, game.settings.height)
    assert initial in VideoScene.RESOLUTIONS

    scene.handle_routed(_confirm())
    initial_index = VideoScene.RESOLUTIONS.index(initial)
    expected = VideoScene.RESOLUTIONS[(initial_index + 1) % len(VideoScene.RESOLUTIONS)]
    assert (game.settings.width, game.settings.height) == expected
    scene.handle_routed(RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD))
    assert (game.settings.width, game.settings.height) == initial

    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD))
    scene.handle_routed(_confirm())
    assert game.settings.fullscreen is True

    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD))
    scene.handle_routed(_confirm())
    assert game.settings.vsync is True

    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD))
    scene.handle_routed(_confirm())
    defaults = UserSettings()
    assert (game.settings.width, game.settings.height) == (
        defaults.width,
        defaults.height,
    )
    assert game.settings.fullscreen is defaults.fullscreen
    assert game.settings.vsync is defaults.vsync
