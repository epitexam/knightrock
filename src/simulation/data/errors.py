"""Shared typed-JSON plumbing for gameplay data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
"""A value as ``json.loads`` can produce, before any gameplay validation."""

__all__ = [
    "GameplayDataError",
    "JsonValue",
    "pair_of_floats",
    "read_bool",
    "read_number",
    "read_numbers",
    "read_optional_string",
    "read_string",
    "read_string_mapping",
    "read_strings",
    "read_int",
    "read_json_object",
    "read_number",
    "reject_unknown",
    "required_field",
    "triple_of_ints",
]


class GameplayDataError(ValueError):
    """A gameplay JSON file is malformed (fail loudly, never guess)."""


def read_json_object(path: str | Path, version: int | tuple[int, ...]) -> dict[str, JsonValue]:
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
    return cast("dict[str, JsonValue]", raw)


def reject_unknown(
    raw: dict[str, JsonValue], allowed: frozenset[str] | set[str], where: str
) -> None:
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


def required_field(mapping: dict[str, JsonValue], key: str, where: str) -> JsonValue:
    """Fetch a mandatory JSON field with a precise location in the error."""
    if key not in mapping:
        raise GameplayDataError(f"{where}: missing required field {key!r}")
    return mapping[key]


# -- shared scalar validators -----------------------------------------------
# A gameplay JSON file is hand-edited. Python's coercions are too forgiving
# for that: bool("false") is True, and float("12") accepts a typo that should
# have been a JSON number. These validators refuse anything but the declared
# JSON type, naming the field in the error.


def read_string(value: JsonValue, where: str) -> str:
    """A JSON string at ``where``."""
    if not isinstance(value, str):
        raise GameplayDataError(f"{where}: expected a string, got {value!r}")
    return value


def read_optional_string(value: JsonValue, where: str) -> str | None:
    """A JSON string or null at ``where``."""
    return None if value is None else read_string(value, where)


def read_strings(value: JsonValue, where: str) -> tuple[str, ...]:
    """A JSON list (or in-code tuple) of strings at ``where``."""
    if not isinstance(value, (list, tuple)):
        raise GameplayDataError(f"{where}: expected a list of strings, got {value!r}")
    return tuple(read_string(item, where) for item in value)


def read_numbers(value: JsonValue, where: str) -> tuple[float, ...]:
    """A JSON list (or in-code tuple) of numbers at ``where``."""
    if not isinstance(value, (list, tuple)):
        raise GameplayDataError(f"{where}: expected a list of numbers, got {value!r}")
    return tuple(read_number(item, where) for item in value)


def read_string_mapping(value: JsonValue, where: str) -> dict[str, str]:
    """A JSON object whose keys and values are strings."""
    if not isinstance(value, dict):
        raise GameplayDataError(f"{where}: expected an object, got {value!r}")
    return {read_string(key, where): read_string(item, where) for key, item in value.items()}


def read_bool(value: JsonValue, where: str) -> bool:
    """A JSON boolean at ``where``; strings such as ``"false"`` are refused."""
    if not isinstance(value, bool):
        raise GameplayDataError(f"{where}: expected a boolean, got {value!r}")
    return value


def read_number(value: JsonValue, where: str) -> float:
    """A JSON number at ``where``; numeric strings and booleans are refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GameplayDataError(f"{where}: expected a number, got {value!r}")
    return float(value)


def read_int(value: JsonValue, where: str) -> int:
    """A JSON integer at ``where``; integral floats are accepted, strings are not."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GameplayDataError(f"{where}: expected an integer, got {value!r}")
    number = float(value)
    if not number.is_integer():
        raise GameplayDataError(f"{where}: expected an integer, got {value!r}")
    return int(number)


# -- shared shape validators ------------------------------------------------
# A gameplay JSON document is hand-edited, so the shapes that appear in more
# than one file get one implementation. `player.json` and `enemies.json` both
# carry `[x, y]` inflates and `[r, g, b]` colors, and both used to have their
# own byte-identical copy of these two, which is a second place to fix a typo
# in an error message and a second thing to keep in step with the schema.


def pair_of_floats(value: JsonValue, where: str) -> tuple[float, float]:
    """An ``[x, y]`` pair, or a ``GameplayDataError`` naming the field."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise GameplayDataError(f"{where}: expected a [x, y] pair, got {value!r}")
    try:
        return (read_number(value[0], where), read_number(value[1], where))
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-numeric pair entry: {value!r}") from exc


def triple_of_ints(value: JsonValue, where: str) -> tuple[int, int, int]:
    """An ``[r, g, b]`` color triple, or a ``GameplayDataError`` naming the field."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise GameplayDataError(f"{where}: expected a [r, g, b] triple, got {value!r}")
    try:
        return (
            read_int(value[0], where),
            read_int(value[1], where),
            read_int(value[2], where),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-integer color entry: {value!r}") from exc
