"""JSON save of the progression (audit F8.1, Phase 2 #6).

``LevelConfig.level_unlock`` — declared in the TMX *Data* layer — was never
read: on level completion, the application layer unlocks the id it points to
and persists the state to a JSON file in the user folder (no file is written
inside the PyInstaller bundle, which may be read-only).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SAVE_FORMAT_VERSION = 1


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
            unlocked = [int(level_id) for level_id in data["unlocked_levels"]]
            if 0 not in unlocked:
                unlocked.append(0)
            return SaveGame(
                unlocked_levels=unlocked,
                last_level_id=int(data["last_level_id"]),
            )
        except KeyError, TypeError, ValueError:
            logger.warning("Corrupted save file, starting from a fresh save")
            return cls()

    def save(self, path: Path) -> None:
        """Write the save as JSON, creating parent directories."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> SaveGame:
        """Read the save from JSON; missing or corrupted files yield a fresh save."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except OSError, json.JSONDecodeError:
            return cls()


def default_save_path() -> Path:
    """User-owned save location (overridable via ``KNIGHTROCK_SAVE_DIR``)."""
    base = Path(os.environ.get("KNIGHTROCK_SAVE_DIR", str(Path.home())))
    return base / ".knightrock" / "savegame.json"
