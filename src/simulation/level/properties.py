"""Reading a level designer's custom properties out of a Tiled object.

A new property in Tiled is a *string* by default, and the world builder used to
hand whatever came back straight to ``float()``. A designer typing ``100`` into
a fresh property therefore crashed the level with a bare ``ValueError`` naming
no object and no property -- the game reached the fatal screen without saying
which of the level's forty hazards was wrong. The same blindness goes the other
way: ``bool("false")`` is ``True``, so a property set to the string ``"false"``
silently *enabled* the thing the designer switched off.

So the conversions live here, they are strict about what they accept, and the
error they raise names the object, the property and the value. ``flip`` in
particular is a Tiled *bool* property, and pytmx already parses those into a
real bool: the string case is a level that was edited by hand, which is worth
saying out loud rather than guessing at.
"""

from typing import Any


class LevelPropertyError(ValueError):
    """A custom property carries a value the game cannot use.

    A ``ValueError`` because that is what the callers used to raise, so the
    fatal screen already handles it; the message is what changed.
    """


def number(properties: dict, key: str, default: float, *, where: str) -> float:
    """``key`` as a float, or ``default`` when the property is absent."""
    value = properties.get(key, default)
    if isinstance(value, bool):
        raise _bad(key, value, "a number", where)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            raise _bad(key, value, "a number", where) from None
    raise _bad(key, value, "a number", where)


def flag(properties: dict, key: str, default: bool, *, where: str) -> bool:
    """``key`` as a bool.

    Tiled stores booleans as booleans, so the only strings that should ever
    arrive here are the ones a hand-edited file carries.
    """
    value = properties.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off", ""):
            return False
        raise _bad(key, value, "true or false", where)
    return bool(value)


def _bad(key: str, value: Any, expected: str, where: str) -> LevelPropertyError:
    return LevelPropertyError(
        f"{where}: property '{key}' is {value!r}, expected {expected}. "
        "Check its type in Tiled -- a new property is a string, and the game "
        "reads it as a number or a bool."
    )
