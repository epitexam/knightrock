"""BUG-02: the debug overlay must be switchable at runtime."""

import pytest

from src.core.settings import Debug


def test_debug_disabled_when_environment_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    assert Debug.is_enabled() is False


def test_debug_enabled_when_environment_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUG", "1")
    assert Debug.is_enabled() is True


def test_debug_flag_is_read_dynamically(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG", raising=False)
    assert Debug.is_enabled() is False

    monkeypatch.setenv("DEBUG", "1")
    assert Debug.is_enabled() is True

    monkeypatch.setenv("DEBUG", "0")
    assert Debug.is_enabled() is False