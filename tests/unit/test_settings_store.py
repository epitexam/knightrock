import json
from pathlib import Path

from src.application.settings_store import SETTINGS_FORMAT_VERSION, SettingsStore, UserSettings


def test_settings_store_roundtrips_video_ui_and_bindings(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = UserSettings(width=1280, height=720, fullscreen=True, vsync=True, ui_scale=1.2)

    store.save(settings)
    loaded = store.load()

    assert loaded == settings
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["version"] == SETTINGS_FORMAT_VERSION
    assert payload["bindings"]["version"] == SETTINGS_FORMAT_VERSION
    assert payload["video"]["width"] == 1280
    assert payload["ui"]["scale"] == 1.2


def test_settings_store_preserves_unknown_sections(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"custom": {"keep": True}}), encoding="utf-8")
    store = SettingsStore(path)

    store.save(UserSettings())

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["custom"] == {"keep": True}


def test_settings_store_invalid_or_missing_values_use_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)

    assert store.load() == UserSettings()

    path.write_text(json.dumps({"version": 1, "video": {"width": 1}}), encoding="utf-8")
    assert store.load() == UserSettings()

    path.write_text("not-json", encoding="utf-8")
    assert store.load() == UserSettings()
