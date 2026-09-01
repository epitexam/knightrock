"""Spatial hash grid for efficient collision detection (PERF-01/02).

This module provides a spatial partitioning system to optimize collision
detection in tile-based games. It divides the game world into a grid of cells,
where each cell contains a list of sprites. This allows for O(1) lookup of
potential collision candidates, regardless of the total number of sprites.
"""

from collections import defaultdict
from typing import Iterable, Protocol

import pygame


class SpatialHashable(Protocol):
    """Protocol for objects that can be stored in the spatial hash."""

    @property
    def hitbox(self) -> pygame.Rect | pygame.FRect:
        """The collision hitbox of the object."""
        ...


class SpatialHash:
    """2D grid for spatial partitioning of collision objects.

    Each cell contains a list of sprites. Queries return sprites from
    the cell and its 8 neighbors (3x3 area), giving O(1) lookup time
    regardless of the total number of sprites.

    This is particularly effective for tile-based games where most
    collision objects (tiles) are static and can be bucketed once at
    level load time.

    Attributes
    ----------
    cell_size : int
        Size of each grid cell in pixels. Larger cells = fewer cells
        but more sprites per cell. 128px is a good default for 64px tiles.
    grid : dict[tuple[int, int], list[SpatialHashable]]
        Mapping of cell coordinates to lists of sprites in that cell.
    """

    def __init__(self, cell_size: int = 128):
        """Initialize the spatial hash with a cell size.

        Args:
            cell_size: Size of each grid cell in pixels. 128px (2x tile size)
                works well for 64px tiles.
        """
        self.cell_size = cell_size
        self.grid: dict[tuple[int, int], list[SpatialHashable]] = defaultdict(list)

    def add(self, sprite: SpatialHashable) -> None:
        """Add a sprite to the grid.

        Args:
            sprite: A sprite with a hitbox property to add to the grid.
        """
        cell = self._get_cell(sprite.hitbox)
        self.grid[cell].append(sprite)

    def add_all(self, sprites: Iterable[SpatialHashable]) -> None:
        """Add multiple sprites to the grid.

        Args:
            sprites: Iterable of sprites to add.
        """
        for sprite in sprites:
            self.add(sprite)

    def clear(self) -> None:
        """Clear all sprites from the grid."""
        self.grid.clear()

    def get_nearby(self, hitbox: pygame.Rect | pygame.FRect) -> list[SpatialHashable]:
        """Get all sprites in the same cell and 8 neighboring cells.

        This returns potential collision candidates. The caller should
        still perform actual collision checks on the returned sprites.

        Args:
            hitbox: The hitbox to query around.

        Returns:
            List of sprites that might collide. May include false positives.
        """
        center_cell = self._get_cell(hitbox)
        nearby: list[SpatialHashable] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cell = (center_cell[0] + dx, center_cell[1] + dy)
                nearby.extend(self.grid.get(cell, []))
        return nearby

    def _get_cell(self, box: pygame.Rect | pygame.FRect) -> tuple[int, int]:
        """Convert a rect's center to grid cell coordinates.

        Args:
            box: A pygame Rect or FRect.

        Returns:
            Tuple of (cell_x, cell_y) coordinates.
        """
        return (
            int(box.centerx // self.cell_size),
            int(box.centery // self.cell_size),
        )
