"""Gameplay JSON is hand-edited: wrong scalar types must fail loudly.

``bool("false")`` is ``True`` in Python, so a designer writing a string where
a boolean is expected used to get the opposite of what they wrote, with no
error. Numeric strings were accepted just as silently. The shipped files load
unchanged; only the type of a value is under test here.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from src.data.errors import GameplayDataError
from src.data.provider import load_gameplay_data
from src.data.roots import GAMEPLAY_SUBDIR

SHIPPED = Path(__file__).resolve().parents[2] / "data" / "gameplay"
FILES = ("attacks.json", "enemies.json", "player.json", "levels.json")


def _copy_and_mutate(tmp_path: Path, mutate: Callable[[Path], None]) -> Path:
    directory = tmp_path / GAMEPLAY_SUBDIR
    directory.mkdir()
    for name in FILES:
        shutil.copy(SHIPPED / name, directory / name)
    mutate(directory)
    return directory


def _first_object_with(document: object, key: str) -> dict[str, object] | None:
    """Find the first mapping carrying ``key``, recursively."""
    if isinstance(document, dict):
        if key in document:
            return document
        for value in document.values():
            found = _first_object_with(value, key)
            if found is not None:
                return found
    elif isinstance(document, list):
        for value in document:
            found = _first_object_with(value, key)
            if found is not None:
                return found
    return None


def _edit(directory: Path, name: str, mutate: Callable[[dict], None]) -> None:
    path = directory / name
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document), encoding="utf-8")


def test_shipped_gameplay_data_still_loads() -> None:
    data = load_gameplay_data(SHIPPED)

    assert data.enemies
    assert data.attack_sets
    assert data.player.health > 0


def test_a_string_boolean_in_enemies_is_refused(tmp_path: Path) -> None:
    def mutate(directory: Path) -> None:
        def change(document: dict) -> None:
            first = next(iter(document["enemies"].values()))
            first["has_ai"] = "false"

        _edit(directory, "enemies.json", change)

    with pytest.raises(GameplayDataError, match="boolean"):
        load_gameplay_data(_copy_and_mutate(tmp_path, mutate))


def test_a_string_boolean_in_attacks_is_refused(tmp_path: Path) -> None:
    def mutate(directory: Path) -> None:
        def change(document: dict) -> None:
            # The boolean is absent from shipped hits and falls back to a
            # default, so add it to the first hit block.
            phase = _first_object_with(document, "hit")
            assert phase is not None
            phase["hit"]["unblockable"] = "false"

        _edit(directory, "attacks.json", change)

    with pytest.raises(GameplayDataError, match="boolean"):
        load_gameplay_data(_copy_and_mutate(tmp_path, mutate))


def test_a_numeric_string_in_player_is_refused(tmp_path: Path) -> None:
    def mutate(directory: Path) -> None:
        _edit(directory, "player.json", lambda document: document["player"].update(health="100"))

    with pytest.raises(GameplayDataError, match="number"):
        load_gameplay_data(_copy_and_mutate(tmp_path, mutate))
