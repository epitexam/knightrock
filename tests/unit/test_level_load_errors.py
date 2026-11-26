"""A level file that is there but unreadable must say which file.

pytmx signs a truncated map with a ``ParseError`` and a missing tileset with a
bare ``Exception``, and neither carries the path -- the fatal screen therefore
printed a message about a syntax problem in a file it never named. The manager
is the one place that knows the path, so it re-raises both under one name that
carries it.
"""

from pathlib import Path

import pytest

from src.core.level.level_manager import LevelLoadError, LevelManager

_TRUNCATED = '<?xml version="1.0"?><map><oops>'

_MISSING_TILESET = (
    '<?xml version="1.0"?><map version="1.0" width="1" height="1" '
    'tilewidth="64" tileheight="64"><tileset firstgid="1" source="gone.tsx"/></map>'
)


def test_a_truncated_map_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "broken.tmx").write_text(_TRUNCATED, encoding="utf-8")
    manager = LevelManager({0: str(tmp_path / "broken.tmx")})

    with pytest.raises(LevelLoadError) as raised:
        manager.get(0)

    assert "broken.tmx" in str(raised.value)


def test_a_missing_tileset_names_the_file(tmp_path: Path) -> None:
    (tmp_path / "nots.tmx").write_text(_MISSING_TILESET, encoding="utf-8")
    manager = LevelManager({0: str(tmp_path / "nots.tmx")})

    with pytest.raises(LevelLoadError) as raised:
        manager.get(0)

    assert "nots.tmx" in str(raised.value)


def test_the_original_cause_is_kept(tmp_path: Path) -> None:
    (tmp_path / "broken.tmx").write_text(_TRUNCATED, encoding="utf-8")
    manager = LevelManager({0: str(tmp_path / "broken.tmx")})

    with pytest.raises(LevelLoadError) as raised:
        manager.get(0)

    assert raised.value.__cause__ is not None


def test_an_internal_failure_is_logged_with_its_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A bug in the adapter must not be silently filed as a bad map file."""
    import logging

    from src.simulation.level import level_manager
    from src.simulation.level.level_data import LevelData

    path = tmp_path / "broken.tmx"
    path.write_text("anything", encoding="utf-8")
    monkeypatch.setattr(level_manager, "load_pygame", lambda _: object())

    def broken(tmx: object) -> LevelData:
        raise RuntimeError("adapter bug")

    monkeypatch.setattr(LevelData, "from_tmx", broken)
    manager = LevelManager({0: str(path)})

    with caplog.at_level(logging.ERROR), pytest.raises(LevelLoadError):
        manager.get(0)

    assert "adapter bug" in caplog.text
    assert "Traceback" in caplog.text


def test_a_level_load_error_is_a_value_error(tmp_path: Path) -> None:
    (tmp_path / "broken.tmx").write_text(_TRUNCATED, encoding="utf-8")
    manager = LevelManager({0: str(tmp_path / "broken.tmx")})

    with pytest.raises(ValueError):
        manager.get(0)
