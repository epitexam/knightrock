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


def _write_v1(tmp_path: Path, *, width: int, height: int, fullscreen: bool) -> Path:
    """A genuine v1 file: a real bindings block with a v1 video section.

    Built from a round-trip and then rewritten, because a hand-written
    ``bindings`` stub is not a bindings block -- and a file that fails to parse
    is indistinguishable, from the loader's side, from one that migrated.
    """
    return _write_legacy(
        tmp_path, 1, {"width": width, "height": height, "fullscreen": fullscreen, "vsync": True}
    )


def _write_v2(tmp_path: Path, **video: object) -> Path:
    """A genuine v2 file, window claims and all."""
    return _write_legacy(tmp_path, 2, video)


def _write_legacy(tmp_path: Path, version: int, video: dict[str, object]) -> Path:
    path = tmp_path / "settings.json"
    payload = UserSettings().to_dict()
    assert isinstance(payload, dict)
    payload["version"] = version
    payload["video"] = video
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_settings_store_roundtrips_video_ui_and_bindings(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    settings = UserSettings(
        window_size=(1600, 900),
        pixel_perfect=True,
        vsync=True,
        frame_limit=144,
        ui_scale=1.2,
    )

    store.save(settings)
    loaded = store.load()

    assert loaded == settings
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["version"] == SETTINGS_FORMAT_VERSION
    assert payload["window"]["size"] == [1600, 900]
    assert payload["video"]["pixel_perfect"] is True
    assert payload["video"]["frame_limit"] == 144
    assert payload["ui"]["scale"] == 1.2


def test_an_old_file_carrying_a_screen_and_a_mode_still_loads(tmp_path: Path) -> None:
    """The keys that named a screen and a display mode were dropped, not banned.

    A settings file written before that still carries them, and refusing to load
    it would cost the player every binding they had rebound -- which is the
    expensive half to rebuild and the half that must never be lost over a video
    key the game no longer knows what to do with.
    """
    payload = UserSettings(
        window_size=(1600, 900), vsync=True, frame_limit=144, pixel_perfect=True
    ).to_dict()
    assert isinstance(payload, dict)
    payload["video"]["display"] = "borderless"
    payload["video"]["monitor"] = "VG271U M3"
    payload["video"]["fullscreen_mode"] = [2560, 1440]
    payload["window"]["position"] = [0, 0]
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = SettingsStore(path).load()

    assert loaded == UserSettings(
        window_size=(1600, 900), vsync=True, frame_limit=144, pixel_perfect=True
    )
    for gone in ("display", "monitor", "fullscreen_mode", "window_position"):
        assert not hasattr(loaded, gone), f"{gone} is gone and cannot come back"


def test_the_saved_file_holds_no_unhonourable_window_claim(tmp_path: Path) -> None:
    """The regression, restated against the claims that survived it.

    This used to be ``test_the_saved_file_holds_no_window_size``, and it was
    right for v3: every key in the file was a claim the game could not check, so
    none of them could be stored. One of them has since been made *checkable*,
    and that is what allows it back:

    - a **window size** is a request the stage clamps to the panel it opens on and
      never writes back, so a size from a 4K desk survives arriving at a laptop
      instead of being overwritten. It is the one window number the player chose,
      and the one number this menu still owns.

    What is still refused is the rest: ``render_scale`` described a fixed render
    target that no longer exists, ``smoothing`` described a per-frame resample
    that no longer happens, and the screen picker and the display mode described a
    request the window manager has the last word on. None has anything to say.
    """
    store = SettingsStore(tmp_path / "settings.json")
    store.save(UserSettings())
    payload = json.loads(store.path.read_text(encoding="utf-8"))

    assert set(payload["video"]) == {
        "pixel_perfect",
        "fit",
        "vsync",
        "frame_limit",
    }
    assert set(payload["window"]) == {"size"}
    for dead in ("width", "height", "size_mode", "render_scale", "smoothing"):
        assert not hasattr(UserSettings(), dead), f"{dead} is gone and cannot come back"
        assert dead not in payload["video"], f"{dead} has nothing left to describe"


def test_a_v2_file_keeps_its_bindings_and_drops_its_window_claims(tmp_path: Path) -> None:
    """An old file loads, and the half that was expensive to rebuild survives.

    The video keys are ignored rather than rejected on purpose. A v2 player who
    rebound their controls should not land on the defaults because of a key the
    game no longer knows what to do with -- and the keys that file still carries
    are precisely the ones that are only claims.
    """
    path = _write_v2(
        tmp_path,
        width=2176,
        height=1224,
        size_mode="manual",
        render_scale=1,
        smoothing=True,
        vsync=True,
        frame_limit=144,
        display="fullscreen",
    )
    before = UserSettings().load() if False else None
    del before
    store = SettingsStore(path)

    loaded = store.load()

    assert loaded.bindings == UserSettings().bindings
    assert not hasattr(loaded, "display")
    assert loaded.vsync is True
    assert loaded.frame_limit == 144
    assert not hasattr(loaded, "width")


def test_uncapped_survives_the_round_trip(tmp_path: Path) -> None:
    """``None`` is a value, not a missing key: the two mean opposite things."""
    store = SettingsStore(tmp_path / "settings.json")

    store.save(UserSettings(frame_limit=None))
    loaded = store.load()

    assert loaded.frame_limit is None
    assert json.loads(store.path.read_text(encoding="utf-8"))["video"]["frame_limit"] is None


def test_a_v1_file_is_read_and_gains_the_new_fields(tmp_path: Path) -> None:
    """A v1 player keeps their controls and takes the default window.

    ``fullscreen: true`` asked the driver for a mode, which is the thing that
    blanks a hybrid-GPU laptop, and the size it also carried came off a fixed
    catalogue. Both are dropped rather than honoured: the game is a resizable
    window now, and a player who wants it big drags it.
    """
    store = SettingsStore(_write_v1(tmp_path, width=1600, height=900, fullscreen=True))

    loaded = store.load()

    assert not hasattr(loaded, "display")
    assert loaded.pixel_perfect is False
    assert loaded.frame_limit == DEFAULT_FRAME_LIMIT
    assert loaded.vsync is True

    store.save(loaded)
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == (
        SETTINGS_FORMAT_VERSION
    ), "saving after a migration upgrades the file"


def test_a_v1_windowed_file_keeps_its_choices(tmp_path: Path) -> None:
    path = _write_v1(tmp_path, width=1280, height=720, fullscreen=False)

    loaded = SettingsStore(path).load()

    assert not hasattr(loaded, "display")
    assert loaded.vsync is True


@pytest.mark.parametrize(
    "video",
    [
        {"frame_limit": 5},
        {"frame_limit": 5000},
        {"pixel_perfect": "yes"},
        {"vsync": 1},
    ],
)
def test_out_of_range_video_values_fall_back_to_defaults(tmp_path: Path, video) -> None:
    path = tmp_path / "settings.json"
    payload = UserSettings().to_dict()
    assert isinstance(payload, dict)
    payload["video"] = video
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert SettingsStore(path).load() == UserSettings()


def test_the_file_is_written_whole_rather_than_merged(tmp_path: Path) -> None:
    """What lands on disk is the current schema, and nothing else.

    The write used to re-read the file, merge the payload into whatever it found
    and replace the result -- which is how an unknown section could survive, and
    also how a save blocked the frame on file I/O. The payload already contains
    every key the schema has, so merging could only ever preserve keys nothing
    reads. A stale ``custom`` block is dropped, and what is in the file is
    exactly what the loader will read back.
    """
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"custom": {"keep": True}}), encoding="utf-8")
    store = SettingsStore(path)

    store.save(UserSettings(ui_scale=1.2))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "custom" not in payload
    assert UserSettings.from_dict(payload) == store.load()


def test_a_failed_read_says_so_in_the_log(tmp_path: Path, caplog) -> None:
    """A settings file that cannot be read used to vanish without a trace.

    Every error was caught and the defaults returned, silently. So a schema that
    stopped matching, a truncated write or a hand edit looked exactly like a
    first launch, and the first change afterwards overwrote the file that still
    held the player's bindings. The defaults are still the answer -- refusing to
    start would be worse -- but the reason has to be on the record.
    """
    path = tmp_path / "settings.json"
    path.write_text('{"version": 2, "video": {"frame_limit": ', encoding="utf-8")
    store = SettingsStore(path)

    with caplog.at_level("ERROR"):
        assert store.load() == UserSettings()

    assert str(path) in caplog.text
    assert "Unable to read the settings" in caplog.text


def test_the_previous_file_is_kept_before_it_is_replaced(tmp_path: Path) -> None:
    """A save keeps what it is about to overwrite, best effort.

    The case this is for is a file that parses and is still wrong -- a schema
    from a build that had a key this one rejects. The player's controls are then
    one rename away, and they were one overwrite away from gone.
    """
    store = SettingsStore(tmp_path / "settings.json")
    first = UserSettings(ui_scale=1.2, frame_limit=144)
    store.save(first)

    store.save(UserSettings(ui_scale=0.8))

    backup = tmp_path / "settings.json.bak"
    assert backup.is_file()
    assert UserSettings.from_dict(json.loads(backup.read_text(encoding="utf-8"))) == first


def test_a_first_launch_writes_nothing_and_says_nothing(tmp_path: Path, caplog) -> None:
    """No file is not an error, and must not look like one in the log."""
    store = SettingsStore(tmp_path / "absent.json")

    with caplog.at_level("ERROR"):
        assert store.load() == UserSettings()

    assert caplog.text == ""


def test_settings_store_invalid_or_missing_values_use_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)

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
