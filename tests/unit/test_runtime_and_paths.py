"""Tests for resource lookup and the top-level game runtime boundary."""

import sys
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

    assert Path(resource_path("assets/data/levels/1.tmx")) == (
        PROJECT_ROOT / "assets/data/levels/1.tmx"
    ).resolve()


def test_resource_path_uses_pyinstaller_bundle_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert Path(resource_path("assets/example.dat")) == (
        tmp_path / "assets/example.dat"
    ).resolve()


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
