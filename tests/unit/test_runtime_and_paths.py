"""Tests for resource lookup and the top-level game runtime boundary."""

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pygame
import pytest

from src.core.game import Game
from src.core.level.level_manager import LevelManager
from src.core.paths import PROJECT_ROOT, resource_path


def test_resource_path_is_independent_from_current_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    assert (
        Path(resource_path("assets/data/levels/1.tmx"))
        == (PROJECT_ROOT / "assets/data/levels/1.tmx").resolve()
    )


def test_resource_path_uses_pyinstaller_bundle_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert Path(resource_path("assets/example.dat")) == (tmp_path / "assets/example.dat").resolve()


def test_level_manager_raises_clear_error_for_missing_level() -> None:
    manager = LevelManager()
    manager.register(99, "assets/data/levels/does_not_exist.tmx")

    with pytest.raises(FileNotFoundError) as exc_info:
        manager.get(99)

    assert "Level file not found" in str(exc_info.value)


def test_run_handles_initialization_errors_and_always_quits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    error = RuntimeError("initialization failed")
    initialize = Mock(side_effect=error)
    handle_fatal_error = Mock()
    quit_pygame = Mock()
    monkeypatch.setattr(game, "_initialize", initialize)
    monkeypatch.setattr(game, "_handle_fatal_error", handle_fatal_error)
    monkeypatch.setattr(pygame, "quit", quit_pygame)

    with pytest.raises(SystemExit) as exit_info:
        game.run()

    assert exit_info.value.code == 1
    handle_fatal_error.assert_called_once_with(error)
    quit_pygame.assert_called_once_with()


def test_run_handles_loop_errors_and_always_quits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    error = RuntimeError("loop failed")
    initialize = Mock()
    run_loop = Mock(side_effect=error)
    handle_fatal_error = Mock()
    quit_pygame = Mock()
    monkeypatch.setattr(game, "_initialize", initialize)
    monkeypatch.setattr(game, "_run_loop", run_loop)
    monkeypatch.setattr(game, "_handle_fatal_error", handle_fatal_error)
    monkeypatch.setattr(pygame, "quit", quit_pygame)

    with pytest.raises(SystemExit) as exit_info:
        game.run()

    assert exit_info.value.code == 1
    initialize.assert_called_once_with()
    handle_fatal_error.assert_called_once_with(error)
    quit_pygame.assert_called_once_with()


def test_run_quits_when_the_event_loop_requests_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    monkeypatch.setattr(game, "_initialize", Mock())
    monkeypatch.setattr(game, "_run_loop", Mock(side_effect=SystemExit))
    quit_pygame = Mock()
    monkeypatch.setattr(pygame, "quit", quit_pygame)

    with pytest.raises(SystemExit):
        game.run()

    quit_pygame.assert_called_once_with()


def test_first_added_joystick_is_assigned_without_private_state_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    joystick = Mock()
    joystick.get_instance_id.return_value = 7
    joystick.get_name.return_value = "Test controller"
    connect_joystick = Mock()
    monkeypatch.setattr(game.input_provider, "connect_joystick", connect_joystick)
    event = pygame.event.Event(pygame.JOYDEVICEADDED, device_index=0)
    monkeypatch.setattr(pygame.event, "get", lambda: [event])
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda _index: joystick)

    game._handle_events()

    assert game.joysticks == {7: joystick}
    connect_joystick.assert_called_once_with(joystick)


def test_second_joystick_is_not_assigned_while_first_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    active = Mock()
    active.get_instance_id.return_value = 7
    second = Mock()
    second.get_instance_id.return_value = 8
    connect_joystick = Mock()
    game.joysticks = {7: active}
    game.input_provider.connect_joystick(active)  # type: ignore[arg-type]
    monkeypatch.setattr(game.input_provider, "connect_joystick", connect_joystick)
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda _index: second)
    monkeypatch.setattr(
        pygame.event,
        "get",
        lambda: [pygame.event.Event(pygame.JOYDEVICEADDED, device_index=1)],
    )

    game._handle_events()

    assert game.joysticks == {7: active, 8: second}
    connect_joystick.assert_not_called()


def test_removed_joystick_is_reassigned_to_remaining_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    removed = Mock()
    removed.get_instance_id.return_value = 7
    removed.get_name.return_value = "Removed controller"
    replacement = Mock()
    replacement.get_instance_id.return_value = 8
    game.joysticks = {7: removed, 8: replacement}
    game.input_provider.connect_joystick(removed)  # type: ignore[arg-type]
    disconnect_joystick = Mock()
    reassign_joystick = Mock()
    monkeypatch.setattr(game.input_provider, "disconnect_joystick", disconnect_joystick)
    monkeypatch.setattr(game.input_provider, "reassign_joystick", reassign_joystick)
    monkeypatch.setattr(
        pygame.event,
        "get",
        lambda: [pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=7)],
    )

    game._handle_events()

    assert game.joysticks == {8: replacement}
    disconnect_joystick.assert_called_once_with(7)
    reassign_joystick.assert_called_once_with({8: replacement})


def test_removing_inactive_joystick_keeps_active_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game()
    active = Mock()
    active.get_instance_id.return_value = 7
    removed = Mock()
    removed.get_instance_id.return_value = 8
    removed.get_name.return_value = "Inactive controller"
    game.joysticks = {7: active, 8: removed}
    game.input_provider.connect_joystick(active)  # type: ignore[arg-type]
    reassign_joystick = Mock()
    monkeypatch.setattr(game.input_provider, "reassign_joystick", reassign_joystick)
    monkeypatch.setattr(
        pygame.event,
        "get",
        lambda: [pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=8)],
    )

    game._handle_events()

    assert game.joysticks == {7: active}
    reassign_joystick.assert_called_once_with({7: active})


def test_game_applies_persisted_video_settings(tmp_path: Path) -> None:
    game = Game(
        save_path=tmp_path / "savegame.json",
        bindings_path=tmp_path / "settings.json",
    )
    game._initialize()

    game.apply_settings(replace(game.settings, width=800, height=600, vsync=True))

    assert game.display_surface is not None
    assert game.display_surface.get_size() == (800, 600)
    assert game.settings.vsync is True
