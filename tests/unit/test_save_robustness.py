"""Progression must survive a crash mid-write and reject nonsense values.

The settings store already writes through a temporary file and a backup; the
progression save used to write in place and accept any integer at all, so a
hand-edited or half-written file could silently reset the player's progress.
"""

import logging
from pathlib import Path

import pytest

from src.application.save_game import SAVE_FORMAT_VERSION, SaveGame
from src.core.atomic_json import write_json_atomic


def test_sanitizes_negative_duplicate_and_missing_ids() -> None:
    save = SaveGame.from_dict(
        {
            "version": SAVE_FORMAT_VERSION,
            "unlocked_levels": [-1, 2, 2, 0],
            "last_level_id": -5,
        }
    )

    assert save.unlocked_levels == [0, 2]
    assert save.last_level_id == 0


def test_a_boolean_is_not_an_accepted_level_id() -> None:
    save = SaveGame.from_dict(
        {"version": SAVE_FORMAT_VERSION, "unlocked_levels": [True], "last_level_id": 0}
    )

    assert save.unlocked_levels == [0]


def test_a_missing_save_is_silent(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A first launch has no save; that is not a corruption to warn about."""

    with caplog.at_level(logging.WARNING):
        save = SaveGame.load(tmp_path / "missing.json")

    assert save == SaveGame()
    assert "save" not in caplog.text.lower()


def test_a_corrupted_save_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "savegame.json"
    path.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        save = SaveGame.load(path)

    assert save == SaveGame()
    assert "save" in caplog.text.lower()


def test_atomic_write_keeps_a_backup(tmp_path: Path) -> None:
    path = tmp_path / "saves" / "savegame.json"
    path.parent.mkdir(parents=True)
    path.write_text("old content", encoding="utf-8")

    write_json_atomic(path, {"version": 1})

    assert path.with_suffix(".json.bak").read_text(encoding="utf-8") == "old content"
    assert '"version": 1' in path.read_text(encoding="utf-8")


def test_atomic_write_removes_its_temporary_on_failure(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        write_json_atomic(tmp_path / "savegame.json", {"bad": object()})

    assert list(tmp_path.glob("tmp*")) == []


def test_settings_save_cleans_its_temporary_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.application.settings_store import SettingsStore, UserSettings

    def broken_dict(self: UserSettings) -> dict[str, object]:
        raise TypeError("cannot serialize")

    monkeypatch.setattr(UserSettings, "to_dict", broken_dict)
    store = SettingsStore(tmp_path / "settings.json")

    with pytest.raises(TypeError):
        store.save(UserSettings())

    assert list(tmp_path.glob("tmp*")) == []
