"""JSON save of the progression.

``LevelConfig.level_unlock`` — declared in the TMX *Data* layer — was never
read: on level completion, the application layer unlocks the id it points to
and persists the state to a JSON file in the user folder (no file is written
inside the PyInstaller bundle, which may be read-only).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.simulation.atomic_json import write_json_atomic

logger = logging.getLogger(__name__)

SAVE_FORMAT_VERSION = 1


def _valid_level_id(value: object) -> bool:
    """Whether ``value`` is a usable level id (a non-negative JSON integer)."""
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


@dataclass
class SaveGame:
    """Persisted progression: unlocked levels and last played level."""

    unlocked_levels: list[int] = field(default_factory=lambda: [0])
    last_level_id: int = 0
    version: int = SAVE_FORMAT_VERSION

    def is_unlocked(self, level_id: int) -> bool:
        """Whether the player may start this level."""
        return level_id in self.unlocked_levels

    def unlock(self, level_id: int) -> bool:
        """Grant access to ``level_id``; return True if it was new."""
        if self.is_unlocked(level_id):
            return False
        self.unlocked_levels.append(level_id)
        return True

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain JSON-compatible dict."""
        return {
            "version": self.version,
            "unlocked_levels": list(self.unlocked_levels),
            "last_level_id": self.last_level_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaveGame:
        """Build a save from a dict; fall back to defaults on any anomaly."""
        try:
            if int(data.get("version", 0)) != SAVE_FORMAT_VERSION:
                raise ValueError("unsupported version")
            raw_ids = data["unlocked_levels"]
            if not isinstance(raw_ids, list):
                raise ValueError("unlocked_levels must be a list")
            # Drop only the unusable entries: one tampered id must not erase
            # every level the player actually unlocked.
            unlocked = sorted(dict.fromkeys(value for value in raw_ids if _valid_level_id(value)))
            if 0 not in unlocked:
                unlocked.insert(0, 0)
            last = data["last_level_id"]
            return SaveGame(
                unlocked_levels=unlocked,
                last_level_id=last if _valid_level_id(last) else 0,
            )
        except KeyError, TypeError, ValueError:
            logger.warning("Corrupted save file, starting from a fresh save")
            return cls()

    def save(self, path: Path) -> None:
        """Write the save atomically, keeping the previous file as a backup."""
        write_json_atomic(path, self.to_dict())

    @classmethod
    def load(cls, path: Path) -> SaveGame:
        """Read the save from JSON; missing or corrupted files yield a fresh save."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except FileNotFoundError:
            # A first launch has no save yet: that is not a problem to report.
            return cls()
        except OSError, json.JSONDecodeError:
            logger.warning(
                "Unable to read the save at %s; starting a fresh one", path, exc_info=True
            )
            return cls()


def default_save_path(environ: Mapping[str, str] | None = None) -> Path:
    """User-owned save location (overridable via ``KNIGHTROCK_SAVE_DIR``)."""
    env = os.environ if environ is None else environ
    base = Path(env.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "savegame.json"
