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
    controls.model.set_items(controls.model.items, 2)  # Jump
    controls.handle_routed(RoutedInput(InputAction.UI_RIGHT, InputDevice.GAMEPAD))
    controls.handle_routed(_confirm())
    controls.handle_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=7))

    assert game.settings.bindings.gameplay.gamepad_buttons[InputAction.JUMP] == 7
    assert game.settings.bindings.gameplay.keyboard[InputAction.JUMP] == pygame.K_SPACE


def test_mouse_binding_is_captured_in_keyboard_column() -> None:
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


def test_video_menu_resizes_width_and_height_with_left_and_right() -> None:
    game = _game()
    scene = VideoScene(game)
    original_width, original_height = game.settings.width, game.settings.height

    scene.handle_routed(_confirm())
    assert game.settings.width == original_width + VideoScene.WIDTH_STEP
    scene.handle_routed(RoutedInput(InputAction.UI_LEFT, InputDevice.GAMEPAD))
    assert game.settings.width == original_width

    scene.handle_routed(RoutedInput(InputAction.UI_DOWN, InputDevice.GAMEPAD))
    scene.handle_routed(_confirm())
    assert game.settings.height == original_height + VideoScene.HEIGHT_STEP
