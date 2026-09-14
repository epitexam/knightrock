"""Typed JSON loader for the level registry (Phase 3 #4).

``levels.json`` is the data-driven replacement for the ``LEVEL_PATHS``
dict hardcoded in ``level_manager.py`` (kept as the built-in fallback)::

    {"version": 1, "levels": {"0": "assets/data/levels/1.tmx", ...}}

Keys are strings in JSON (JSON object keys are always strings); they must
parse as integers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.data.errors import GameplayDataError, read_json_object

LEVELS_FILENAME = "levels.json"
LEVELS_VERSION = 1


def read_levels_file(path: str | Path) -> dict[int, str]:
    """Load the ``id -> TMX path`` registry from a ``levels.json`` file."""
    raw = read_json_object(path, LEVELS_VERSION)
    raw_levels = raw.get("levels")
    if not isinstance(raw_levels, dict):
        raise GameplayDataError(f"{path}: 'levels' must be an object")
    levels: dict[int, str] = {}
    for raw_id, raw_path in raw_levels.items():
        try:
            level_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise GameplayDataError(f"{path}: level id {raw_id!r} is not an integer") from exc
        if not isinstance(raw_path, str) or not raw_path:
            raise GameplayDataError(f"{path}: level {level_id} path must be a string")
        levels[level_id] = raw_path
    return levels


def levels_to_dict(levels: dict[int, str]) -> dict[str, Any]:
    """Serialize an id -> path registry back to its JSON shape."""
    return {
        "version": LEVELS_VERSION,
        "levels": {str(level_id): path for level_id, path in levels.items()},
    }
