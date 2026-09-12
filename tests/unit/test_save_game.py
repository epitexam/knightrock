"""Tests de la sauvegarde JSON (audit F8.1, Phase 2 #6)."""

import json
from pathlib import Path

import pytest

from src.application.save_game import SAVE_FORMAT_VERSION, SaveGame, default_save_path


def test_fresh_save_unlocks_only_the_first_level() -> None:
    save = SaveGame()

    assert save.unlocked_levels == [0]
    assert save.is_unlocked(0)
    assert not save.is_unlocked(1)


def test_unlock_is_idempotent_and_reports_new_unlocks() -> None:
    save = SaveGame()

    assert save.unlock(1) is True
    assert save.unlock(1) is False
    assert save.is_unlocked(1)


def test_roundtrip_through_dict() -> None:
    save = SaveGame(unlocked_levels=[0, 2, 5], last_level_id=2)

    restored = SaveGame.from_dict(save.to_dict())

    assert restored == save


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    save = SaveGame(unlocked_levels=[0, 1], last_level_id=1)
    path = tmp_path / "saves" / "savegame.json"

    save.save(path)
    loaded = SaveGame.load(path)

    assert loaded == save


def test_load_missing_file_returns_fresh_save(tmp_path: Path) -> None:
    assert SaveGame.load(tmp_path / "missing.json") == SaveGame()


def test_load_corrupted_file_returns_fresh_save(tmp_path: Path) -> None:
    path = tmp_path / "savegame.json"
    path.write_text("{not json", encoding="utf-8")

    assert SaveGame.load(path) == SaveGame()


def test_load_unsupported_version_returns_fresh_save(tmp_path: Path) -> None:
    path = tmp_path / "savegame.json"
    path.write_text(json.dumps({"version": 999, "unlocked_levels": [0, 3], "last_level_id": 3}))

    save = SaveGame.load(path)

    assert save == SaveGame()


def test_from_dict_without_first_level_restores_it() -> None:
    save = SaveGame.from_dict(
        {"version": SAVE_FORMAT_VERSION, "unlocked_levels": [3], "last_level_id": 3}
    )

    assert 0 in save.unlocked_levels


def test_default_save_path_lives_in_user_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KNIGHTROCK_SAVE_DIR", raising=False)
    monkeypatch.setenv("HOME", "/tmp/fake-home")

    path = default_save_path()

    assert path == Path("/tmp/fake-home/.knightrock/savegame.json")


def test_default_save_path_honors_the_override_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("KNIGHTROCK_SAVE_DIR", str(tmp_path))

    assert default_save_path() == tmp_path / ".knightrock" / "savegame.json"
