"""Shared typed-JSON plumbing for gameplay data (Phase 3 #4)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GameplayDataError(ValueError):
    """A gameplay JSON file is malformed (fail loudly, never guess)."""


def read_json_object(path: str | Path, version: int | tuple[int, ...]) -> dict[str, Any]:
    """Load a JSON object file and check its ``version`` field.

    Raises
    ------
    FileNotFoundError
        The file does not exist (caller decides whether to fall back).
    GameplayDataError
        The JSON is invalid, is not an object, or carries an unsupported
        version.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GameplayDataError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{path}: top-level value must be an object")
    supported = (version,) if isinstance(version, int) else version
    if raw.get("version") not in supported:
        expected = ", ".join(str(value) for value in supported)
        raise GameplayDataError(
            f"{path}: unsupported version {raw.get('version')!r} (expected {expected})"
        )
    return raw


def reject_unknown(raw: dict[str, Any], allowed: frozenset[str] | set[str], where: str) -> None:
    """Refuse any key the reader below does not read.

    A typo in a hand-edited balance file must fail loudly. Silently defaulting
    it is the worst outcome available: the game boots, the attack or the enemy
    still exists, and the field that was meant to change it quietly did not -- so
    a designer tuning a number sees no effect and concludes the number is wrong.

    The message names the accepted keys alongside the refused one, because the
    reader's own failure mode is a near-miss spelling and the fix is a list to
    pick from, not a pointer to the source.

    Lives here rather than in one loader because the promise is made about the
    whole ``src/data`` package (``__init__`` and ``README`` both state it), and
    a check that had to be repeated per file is a check that would eventually
    be missed in one of them.
    """
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise GameplayDataError(
            f"{where}: unknown field(s) {', '.join(repr(key) for key in unknown)}; "
            f"expected one of {', '.join(sorted(allowed))}"
        )


# -- shared shape validators ------------------------------------------------
# A gameplay JSON document is hand-edited, so the shapes that appear in more
# than one file get one implementation. `player.json` and `enemies.json` both
# carry `[x, y]` inflates and `[r, g, b]` colors, and both used to have their
# own byte-identical copy of these two, which is a second place to fix a typo
# in an error message and a second thing to keep in step with the schema.


def pair_of_floats(value: Any, where: str) -> tuple[float, float]:
    """An ``[x, y]`` pair, or a ``GameplayDataError`` naming the field."""
    if not isinstance(value, list) or len(value) != 2:
        raise GameplayDataError(f"{where}: expected a [x, y] pair, got {value!r}")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-numeric pair entry: {value!r}") from exc


def triple_of_ints(value: Any, where: str) -> tuple[int, int, int]:
    """An ``[r, g, b]`` color triple, or a ``GameplayDataError`` naming the field."""
    if not isinstance(value, list) or len(value) != 3:
        raise GameplayDataError(f"{where}: expected a [r, g, b] triple, got {value!r}")
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-integer color entry: {value!r}") from exc
