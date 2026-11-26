"""The level registry is data, so its paths are validated when read.

A hand-edited ``levels.json`` is the entry point for PyTMX, which parses XML
and tilesets.  Accepting an arbitrary string there would let a relative
``..`` or an absolute path escape the resource root, and two spellings of the
same numeric id would silently overwrite one another.
"""

import json
from pathlib import Path

import pytest

from src.simulation.data.errors import GameplayDataError
from src.simulation.data.levels import read_levels_file


def _registry(tmp_path: Path, levels: dict[str, str]) -> Path:
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({"version": 1, "levels": levels}), encoding="utf-8")
    return path


def test_a_regular_registry_loads(tmp_path: Path) -> None:
    path = _registry(tmp_path, {"0": "assets/data/levels/1.tmx"})

    assert read_levels_file(path) == {0: "assets/data/levels/1.tmx"}


def test_two_spellings_of_the_same_id_are_refused(tmp_path: Path) -> None:
    path = _registry(
        tmp_path,
        {"0": "assets/data/levels/1.tmx", "00": "assets/data/levels/2.tmx"},
    )

    with pytest.raises(GameplayDataError, match="duplicate"):
        read_levels_file(path)


def test_a_path_without_a_tmx_extension_is_refused(tmp_path: Path) -> None:
    path = _registry(tmp_path, {"0": "assets/data/levels/readme.txt"})

    with pytest.raises(GameplayDataError, match=r"\.tmx"):
        read_levels_file(path)


def test_a_traversing_path_is_refused(tmp_path: Path) -> None:
    path = _registry(tmp_path, {"0": "../../etc/passwd.tmx"})

    with pytest.raises(GameplayDataError, match="relative"):
        read_levels_file(path)


def test_an_absolute_path_is_refused(tmp_path: Path) -> None:
    path = _registry(tmp_path, {"0": "/etc/passwd.tmx"})

    with pytest.raises(GameplayDataError, match="relative"):
        read_levels_file(path)
