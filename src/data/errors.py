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
