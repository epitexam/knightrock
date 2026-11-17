"""Reading a level designer's properties must not crash or guess silently.

Tiled types a new custom property as a *string*, and the world builder used to
hand it straight to ``float()``: a level where somebody typed ``100`` into a
fresh ``speed`` reached the fatal screen naming no object. The reverse failure
was quieter still -- ``bool("false")`` is ``True``, so a ``flip`` set to the
string ``"false"`` silently switched the thing *on*.
"""

import pytest

from src.core.level import properties as props


def test_a_string_number_is_read_as_the_number_it_writes() -> None:
    assert props.number({"speed": "100"}, "speed", 50, where="a saw") == 100.0
    assert props.number({"speed": 12}, "speed", 50, where="a saw") == 12.0


def test_an_absent_property_keeps_its_default() -> None:
    assert props.number({}, "speed", 50, where="a saw") == 50.0


def test_a_string_false_does_not_mean_true() -> None:
    """The one that reads as a switch silently turned the wrong way."""
    assert props.flag({"flip": "false"}, "flip", True, where="a saw") is False
    assert props.flag({"flip": "true"}, "flip", False, where="a saw") is True


def test_a_real_bool_is_passed_through() -> None:
    assert props.flag({"flip": False}, "flip", True, where="a saw") is False
    assert props.flag({}, "flip", True, where="a saw") is True


def test_a_bool_where_a_number_belongs_is_refused() -> None:
    """``True`` is an ``int`` in Python, so it used to arrive as ``1.0``."""
    with pytest.raises(props.LevelPropertyError):
        props.number({"speed": True}, "speed", 50, where="a saw")


def test_the_error_names_the_object_and_the_property() -> None:
    with pytest.raises(props.LevelPropertyError) as raised:
        props.number({"speed": "fast"}, "speed", 50, where="a saw object at (32, 64)")
    message = str(raised.value)
    assert "saw" in message
    assert "speed" in message
    assert "fast" in message


def test_the_error_is_a_value_error_so_the_fatal_screen_still_catches_it() -> None:
    with pytest.raises(ValueError):
        props.number({"speed": "fast"}, "speed", 50, where="a saw")
