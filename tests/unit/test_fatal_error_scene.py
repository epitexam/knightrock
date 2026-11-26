"""The last screen keeps the traceback readable and the two exits reachable.

The fatal log is the artifact; the screen is a courtesy on top of it. These
tests use a real runtime with the versioned font but no world assets, so they
also run on a fresh checkout where ``assets/graphics`` is absent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pygame

from src.application.scenes.fatal_error_scene import FatalErrorScene
from src.platform.input.event_router import InputDevice, RoutedInput
from src.shared.input_actions import InputAction

TRACE = "Traceback (most recent call last):\n" + "\n".join(
    f'  File "src/module_{index}.py", line {index}, in a_very_long_function_name'
    for index in range(120)
)


def _scene(tmp_path: Path, trace: str = TRACE):
    from src.application.game import Game

    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    quit_game, to_menu = Mock(), Mock()
    scene = FatalErrorScene(game, trace, on_quit=quit_game, on_menu=to_menu)
    scene.draw(game.render_target)
    return game, scene, quit_game, to_menu


def _route(scene: FatalErrorScene, action: InputAction, **kwargs) -> str | None:
    return scene.handle_routed(RoutedInput(action=action, device=InputDevice.KEYBOARD, **kwargs))


def test_the_traceback_scrolls_with_keys_wheel_pages_and_the_rail(tmp_path: Path) -> None:
    _game, scene, _, _ = _scene(tmp_path)

    assert scene._rail is not None, "a long traceback needs a rail"
    assert scene._scroll == 0
    _route(scene, InputAction.UI_DOWN)
    assert scene._scroll > 0
    _route(scene, InputAction.UI_SCROLL, value=3)
    assert scene._scroll > 0
    after_wheel = scene._scroll
    _route(scene, InputAction.UI_PAGE_DOWN)
    after_page = scene._scroll
    assert after_page > after_wheel
    _route(scene, InputAction.UI_UP)
    assert scene._scroll < after_page

    rail = scene._rail
    scene.handle_routed(
        RoutedInput(
            action=InputAction.UI_POINTER_DOWN,
            device=InputDevice.MOUSE,
            position=(rail.x, rail.bottom - 1),
        )
    )
    assert scene._scroll > after_wheel


def test_only_the_two_buttons_activate(tmp_path: Path) -> None:
    game, scene, quit_game, to_menu = _scene(tmp_path)

    for action, callback in (("quit", quit_game), ("menu", to_menu)):
        index = next(i for i, item in enumerate(scene.model.items) if item.action == action)
        rect = scene.view.item_rects[index]
        scene.handle_routed(
            RoutedInput(
                action=InputAction.UI_POINTER_DOWN,
                device=InputDevice.MOUSE,
                position=rect.center,
            )
        )
        callback.assert_called_once_with()

    quit_game.reset_mock()
    assert scene._area is not None
    scene.handle_routed(
        RoutedInput(
            action=InputAction.UI_POINTER_DOWN,
            device=InputDevice.MOUSE,
            position=scene._area.center,
        )
    )
    quit_game.assert_not_called(), "a click in the traceback does nothing"


def test_back_quits_and_an_unplugged_pad_does_not(tmp_path: Path) -> None:
    _game, scene, quit_game, _ = _scene(tmp_path)

    _route(scene, InputAction.UI_BACK)
    quit_game.assert_called_once_with()
    quit_game.reset_mock()
    scene.handle_routed(
        RoutedInput(
            action=InputAction.UI_BACK, device=InputDevice.GAMEPAD, variant="device_removed"
        )
    )
    quit_game.assert_not_called()


def test_resizing_and_scaling_rebuild_the_trace_without_overflow(tmp_path: Path) -> None:
    game, scene, _, _ = _scene(tmp_path)

    first = scene._trace
    assert first is not None
    scene.set_ui_scale(game.ui_scale * 1.2)
    scene.set_surface(pygame.Surface((640, 360)))
    scene.draw(game.render_target)
    assert scene._trace is not first
    assert scene._trace is not None
    assert scene._scroll <= max(
        0, scene._trace.get_height() - (scene._area.height if scene._area else 0)
    )


def test_the_opening_key_cannot_quit_immediately(tmp_path: Path) -> None:
    from src.application.game import Game

    game = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    game._initialize()
    quit_game, to_menu = Mock(), Mock()
    scene = FatalErrorScene(game, "boom", on_quit=quit_game, on_menu=to_menu, grace=0.35)
    scene.draw(game.render_target)

    scene.handle_routed(RoutedInput(action=InputAction.UI_CONFIRM, device=InputDevice.KEYBOARD))
    quit_game.assert_not_called(), "the key that crashed the game must not press quit for us"

    scene.update(1.0)
    scene.handle_routed(RoutedInput(action=InputAction.UI_CONFIRM, device=InputDevice.KEYBOARD))
    quit_game.assert_called_once_with()


def test_a_short_trace_has_no_rail(tmp_path: Path) -> None:
    _game, scene, _, _ = _scene(tmp_path, "RuntimeError: boom")

    assert scene._rail is None
    assert scene._scroll == 0
