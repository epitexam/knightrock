"""
Manages level loading and caching with automatic progression.
"""

from collections.abc import Mapping
from pathlib import Path

from pytmx.util_pygame import load_pygame

from src.core.level.level_data import LevelData
from src.core.paths import resource_path

LEVEL_PATHS: dict[int, str] = {
    0: "assets/data/levels/1.tmx",
}
"""Déclaration des niveaux : map ``id -> chemin TMX`` (audit F8.1, Phase 2 #4).

Remplace les appels impératifs ``level_manager.register(0, ...)`` : un
nouveau niveau se déclare ici (et sa progression ``level_unlock`` dans
les propriétés TMX du calque *Data*), sans toucher au code du jeu.
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

    def get(self, level_id: int) -> LevelData:
        """
        Retrieve parsed level data, loading it if not yet cached.

        Args:
            level_id: The numeric ID of the level.

        Returns:
            The parsed LevelData object.
        """
        if level_id not in self._cache:
            absolute_path = resource_path(self.level_paths[level_id])
            if not Path(absolute_path).exists():
                raise FileNotFoundError(
                    f"Level file not found: {absolute_path}. "
                    "The 'assets/' directory is required at runtime and must "
                    "be present (clone the repository with assets, or restore "
                    "the missing file)."
                )
            tmx_map = load_pygame(absolute_path)
            self._cache[level_id] = LevelData.from_tmx(tmx_map)
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
