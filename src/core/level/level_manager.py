"""Manages level loading and caching with automatic progression."""

from collections.abc import Mapping
from pathlib import Path

from pytmx.util_pygame import load_pygame

from src.core.level.level_data import LevelData
from src.core.level.properties import LevelPropertyError
from src.core.paths import resource_path

LEVEL_PATHS: dict[int, str] = {
    0: "assets/data/levels/1.tmx",
}
"""Level registry: map ``id -> TMX path`` (audit F8.1, Phase 2 #4).

Replaces imperative ``level_manager.register(0, ...)`` calls: a new level is
declared here (and its ``level_unlock`` progression in the TMX *Data* layer
properties), without touching game code.
"""


class UnknownLevelError(LookupError):
    """A level id was requested that is not in the registry.

    A ``LookupError`` rather than a bare ``KeyError`` because the two failures
    a caller can hit here are not interchangeable: a registered id whose file
    is missing is a broken installation (``FileNotFoundError``), whereas an
    unregistered id is a bad reference -- typically a save file written by a
    build that shipped a level this one no longer has. The message names the
    known ids, because the id that failed is not the interesting part.
    """

    def __init__(self, level_id: int, known_ids: list[int]) -> None:
        self.level_id = level_id
        self.known_ids = tuple(known_ids)
        known = ", ".join(str(known_id) for known_id in self.known_ids) or "none"
        super().__init__(
            f"Unknown level id {level_id!r}; registered levels: {known}. "
            "A save file written by a build that shipped more levels than this "
            "one references an id that no longer exists."
        )


class LevelLoadError(ValueError):
    """The level file is there, but it cannot be turned into a level.

    pytmx signals a truncated map with a ``ParseError`` and a missing tileset
    with a bare ``Exception``, neither of which says anything about which map
    was being read. ``LevelManager`` is the one place that knows, so this is
    where the path and the original cause are attached. A ``ValueError`` so
    that a caller which already handled a bad value keeps handling it.
    """


class LevelManager:
    """
    Loads and caches level data from disk.

    Levels are registered by numeric ID and loaded on demand.
    Provides a mechanism to advance to the next level in registration order.
    """

    def __init__(self, level_paths: Mapping[int, str] | None = None):
        self.level_paths: dict[int, str] = dict(level_paths) if level_paths else {}
        self._cache: dict[int, LevelData] = {}

    def register(self, level_id: int, path: str) -> None:
        """
        Register a level file with a unique ID.

        Args:
            level_id: Numeric identifier for the level.
            path: File system path to the .tmx file.
        """
        self.level_paths[level_id] = path

    def invalidate(self) -> None:
        """Drop every cached level, so the next :meth:`get` re-reads it.

        PyTMX converts each tile against the display format that was current at
        load time. A display change makes those surfaces stale, and the cache
        would keep handing them back for the rest of the session.
        """
        self._cache.clear()

    def get(self, level_id: int) -> LevelData:
        """
        Retrieve parsed level data, loading it if not yet cached.

        Args:
            level_id: The numeric ID of the level.

        Returns:
            The parsed LevelData object.

        Raises:
            UnknownLevelError: ``level_id`` is not in the registry.
            FileNotFoundError: The level is registered but its file is missing.
            LevelLoadError: The file is there but cannot be turned into a level.
        """
        if level_id not in self._cache:
            if level_id not in self.level_paths:
                raise UnknownLevelError(level_id, sorted(self.level_paths))
            absolute_path = resource_path(self.level_paths[level_id])
            if not Path(absolute_path).exists():
                raise FileNotFoundError(
                    f"Level file not found: {absolute_path}. "
                    "The 'assets/' directory is required at runtime and must "
                    "be present (clone the repository with assets, or restore "
                    "the missing file)."
                )
            try:
                tmx_map = load_pygame(absolute_path)
                level_data = LevelData.from_tmx(tmx_map)
            except LevelPropertyError:
                raise
            except Exception as error:  # noqa: BLE001 - pytmx raises bare types
                raise LevelLoadError(f"{absolute_path} cannot be loaded: {error}") from error
            self._cache[level_id] = level_data
        return self._cache[level_id]

    def next_id(self, level_id: int) -> int | None:
        """
        Return the next registered level ID in ascending order.

        Args:
            level_id: The current level ID.

        Returns:
            The next ID if it exists, otherwise None.
        """
        ordered_ids = sorted(self.level_paths.keys())
        if level_id not in ordered_ids:
            return None
        index = ordered_ids.index(level_id)
        if index + 1 < len(ordered_ids):
            return ordered_ids[index + 1]
        return None
