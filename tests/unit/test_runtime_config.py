"""The environment is read into one immutable config at the entry point."""

import os
from pathlib import Path

import pytest

from src.application.game import Game
from src.application.runtime_config import RuntimeConfig


def test_environment_is_read_into_the_config() -> None:
    config = RuntimeConfig.from_environment(
        {
            "DEBUG": "1",
            "DEBUG_COMBAT_DUMP": "1",
            "KNIGHTROCK_DATA_DIR": "/mods",
            "KNIGHTROCK_SAVE_DIR": "/saves",
            "KNIGHTROCK_EXPORT_DIR": "/exports",
        }
    )

    assert config.debug is True
    assert config.combat_dump is True
    assert config.data_dir == Path("/mods")
    assert config.save_dir == Path("/saves")
    assert config.export_dir == Path("/exports")
    assert config.save_path == Path("/saves/.knightrock/savegame.json")
    assert config.settings_path == Path("/saves/.knightrock/settings.json")


def test_missing_overrides_fall_back_to_the_home_directory() -> None:
    config = RuntimeConfig.from_environment({})

    assert config.debug is False
    assert config.data_dir is None
    assert config.save_dir == Path.home()


def test_sdl_hints_are_applied_before_the_display_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDL_VIDEO_HIDPI", raising=False)
    config = RuntimeConfig.from_environment({})

    config.apply_sdl_hints()

    assert os.environ["SDL_VIDEO_HIDPI"] == "1"


def test_game_uses_the_configured_user_files(tmp_path: Path) -> None:
    config = RuntimeConfig.from_environment({"KNIGHTROCK_SAVE_DIR": str(tmp_path)})
    game = Game(config=config)

    assert game._save_path == config.save_path  # noqa: SLF001 - the path under test
    assert game.settings_store.path == config.settings_path
