import json
from pathlib import Path

import pytest

from src.application.settings_store import (
    DEFAULT_FRAME_LIMIT,
    FRAME_LIMITS,
    SETTINGS_FORMAT_VERSION,
    SettingsStore,
    UserSettings,
)
from src.core.display.mode import DisplayMode
from src.core.display.size_mode import SizeMode
from src.core.display.viewport import DEFAULT_RENDER_SCALE


def _write_v1(tmp_path: Path, *, width: int, height: int, fullscreen: bool) -> Path:
    """A genuine v1 file: a real bindings block with a v1 video section.

    Built from a v2 round-trip and then rewritten, because a hand-written
    ``bindings`` stub is not a bindings block -- and a file that fails to parse
    is indistinguishable, from the loader's side, from one that migrated.
    """
    path = tmp_path / "settings.json"
    payload = UserSettings().to_dict()
    assert isinstance(payload, dict)
    payload["version"] = 1
    payload["video"] = {
        "width": width,
        "height": height,
        "fullscreen": fullscreen,
        "vsync": True,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_settings_store_roundtrips_video_ui_and_bindings(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = UserSettings(
        display=DisplayMode.WINDOW,
        width=1280,
        height=720,
        size_mode=SizeMode.MANUAL,
        render_scale=3,
        smoothing=False,
        vsync=True,
        frame_limit=144,
        ui_scale=1.2,
    )

    store.save(settings)
    loaded = store.load()

    assert loaded == settings
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["version"] == SETTINGS_FORMAT_VERSION
    assert payload["video"]["display"] == "window"
    assert payload["video"]["size_mode"] == "manual"
    assert payload["video"]["frame_limit"] == 144
    assert payload["ui"]["scale"] == 1.2


def test_uncapped_survives_the_round_trip(tmp_path: Path) -> None:
    """``None`` is a value, not a missing key: the two mean opposite things."""
    store = SettingsStore(tmp_path / "settings.json")

    store.save(UserSettings(frame_limit=None))
    loaded = store.load()

    assert loaded.frame_limit is None
    assert json.loads(store.path.read_text(encoding="utf-8"))["video"]["frame_limit"] is None


def test_a_v1_file_is_read_and_gains_the_new_fields(tmp_path: Path) -> None:
    """A v1 player who asked for fullscreen gets borderless, not a mode change.

    That mapping is a decision, not a rename: v1 fullscreen asked the driver
    for a mode, which is the thing that blanks a hybrid-GPU laptop. And the size
    becomes MANUAL, because a v1 size is a number the player picked off a fixed
    list and honouring the intent is the honest reading.
    """
    store = SettingsStore(_write_v1(tmp_path, width=1600, height=900, fullscreen=True))

    loaded = store.load()

    assert loaded.display is DisplayMode.BORDERLESS
    assert (loaded.width, loaded.height) == (1600, 900)
    assert loaded.size_mode is SizeMode.MANUAL
    assert loaded.render_scale == DEFAULT_RENDER_SCALE
    assert loaded.smoothing is True
    assert loaded.frame_limit == DEFAULT_FRAME_LIMIT
    assert loaded.vsync is True

    store.save(loaded)
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == (
        SETTINGS_FORMAT_VERSION
    ), "saving after a migration upgrades the file"


def test_a_v1_windowed_file_becomes_a_window(tmp_path: Path) -> None:
    path = _write_v1(tmp_path, width=1280, height=720, fullscreen=False)

    assert SettingsStore(path).load().display is DisplayMode.WINDOW


@pytest.mark.parametrize(
    "video",
    [
        {"render_scale": 4},
        {"render_scale": 0},
        {"frame_limit": 5},
        {"frame_limit": 5000},
        {"display": "holographic"},
        {"size_mode": "whatever"},
        {"smoothing": "yes"},
    ],
)
def test_out_of_range_video_values_fall_back_to_defaults(tmp_path: Path, video) -> None:
    path = tmp_path / "settings.json"
    payload = UserSettings().to_dict()
    assert isinstance(payload, dict)
    payload["video"] = video
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert SettingsStore(path).load() == UserSettings()


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

    # A width of 1 is below the floor, so the file is rejected outright rather
    # than half-read.
    path.write_text(json.dumps({"version": 1, "video": {"width": 1}}), encoding="utf-8")
    assert store.load() == UserSettings()

    path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    assert store.load() == UserSettings()

    path.write_text("not-json", encoding="utf-8")
    assert store.load() == UserSettings()


def test_the_frame_limit_ladder_covers_the_screen_the_player_has() -> None:
    """The first real session this ran on was a 180Hz panel, and the ladder
    stopped at 144 -- so the one rate the player was looking at was the one they
    could not select."""
    from src.core.display.detection import desktop_refresh_rates

    rates = [rate for rate in desktop_refresh_rates() if rate > 0]
    for rate in rates:
        assert rate in FRAME_LIMITS, (
            f"a {rate}Hz display is attached and {rate} is not offered; the video menu "
            "shows the real rate, so a player would see a number they cannot pick"
        )


def test_the_ladder_keeps_the_tick_aligned_values_first() -> None:
    """Below 60 the values must divide the tick rate, or a frame runs a
    fractional number of simulation steps."""
    assert FRAME_LIMITS[1:4] == (20, 30, 60)
    assert None in FRAME_LIMITS, "uncapped has to be reachable"
