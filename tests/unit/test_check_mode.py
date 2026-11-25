"""The one-off ``--check`` command: one boot, one frame, one stderr report."""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest

import main
from src.application.game import Game


def _fake_game(
    monkeypatch: pytest.MonkeyPatch,
    *,
    boot_error: Exception | None = None,
    step_error: Exception | None = None,
) -> Mock:
    game = Mock(spec=Game)
    game.bootstrap.side_effect = boot_error
    game.step.side_effect = step_error
    monkeypatch.setattr(main, "_setup_logging", Mock())
    monkeypatch.setattr(main.RuntimeConfig, "from_environment", Mock(return_value=object()))
    monkeypatch.setattr(main, "Game", Mock(return_value=game))
    return game


def test_check_draws_one_frame_then_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    game = _fake_game(monkeypatch)

    with caplog.at_level(logging.CRITICAL):
        main._run_from_argv(["main.py", "--check"])

    game.bootstrap.assert_called_once_with()
    game.step.assert_called_once_with()
    game.shutdown.assert_called_once_with()
    assert not [record for record in caplog.records if record.levelno >= logging.CRITICAL]


def test_check_reports_a_broken_frame_on_stderr(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    game = _fake_game(monkeypatch, step_error=RuntimeError("no assets"))

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as exit_info:
        main._run_from_argv(["main.py", "--check"])

    assert exit_info.value.code == 1
    game.shutdown.assert_called_once_with()
    assert "Fatal error; the game cannot continue" in caplog.text
    assert "RuntimeError: no assets" in caplog.text


def test_check_reports_a_failed_boot(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    game = _fake_game(monkeypatch, boot_error=FileNotFoundError("assets/data/levels/1.tmx"))

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as exit_info:
        main._run_from_argv(["main.py", "--check"])

    assert exit_info.value.code == 1
    game.step.assert_not_called()
    game.shutdown.assert_called_once_with()
    assert "FileNotFoundError" in caplog.text
