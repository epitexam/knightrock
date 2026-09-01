"""Spatial hash grid for efficient collision detection (PERF-01/02).

The world is divided into square cells; each collidable sprite is registered
in **every cell its collision box (hitbox or rect) overlaps** and a query
visits every cell covered by its own slightly-inflated hitbox. Lookups stay
local (a handful of cells) instead of scanning every tile, while never
missing a sprite that spans several cells or rests exactly on a cell
boundary.

Lifecycle
---------
- Static geometry (tiles) is bucketed once at level load: ``add``/``add_all``.
- Sprites that move (moving platforms) must be re-bucketed each tick with
  ``update`` / ``update_all``; a stale bucket would hide them from queries.
- ``add`` is idempotent; ``remove`` unregisters a sprite from the cells it
  occupies; ``clear`` empties the grid.

``get_nearby`` may return false positives (callers re-check candidates with
real collision tests) but must not return false negatives: the query box is
inflated by ``QUERY_MARGIN_PX`` so a sprite resting exactly on a surface, or
reached within one tick of movement, is still found.

Cell-size selection
-------------------
A cell size of roughly ``1.5×`` to ``2×`` the largest expected object works
well: large enough that most objects touch few cells (cheap inserts/queries),
small enough that each cell holds few members (cheap per-cell scans).  The
default **128 px** suits 64 px tiles and 48×56 px entities, while keeping
``QUERY_MARGIN_PX`` (32) below one cell so a single-cell query still captures
the margin band.
"""

from collections import defaultdict
from math import ceil, floor
from typing import Iterable, Protocol

import pygame

__all__ = [
    "QUERY_MARGIN_PX",
    "SpatialHash",
    "SpatialHashable",
    "RectHashable",
    "SpatialHashMember",
]

# Cell-coverage margin for queries. Must stay >= the maximum distance an
# entity travels in one tick (MAX_FALL_SPEED 1500 px/s / 60 Hz ~= 25 px) plus
# a small rest epsilon, so the per-tick cached query cannot miss a sprite
# reached mid-substep or touched exactly at a cell boundary.
QUERY_MARGIN_PX = 32.0


class SpatialHashable(Protocol):
    """Object exposing a ``hitbox`` (entities, moving platforms)."""

    @property
    def hitbox(self) -> pygame.Rect | pygame.FRect:
        """The collision hitbox of the object."""
        ...


class RectHashable(Protocol):
    """Object exposing only a ``rect`` (e.g. terrain tiles)."""

    @property
    def rect(self) -> pygame.Rect | pygame.FRect:
        """The collision box of the object."""
        ...


# Anything bucketable in the grid: a hitbox or a rect.  The runtime derives
# the box with ``getattr(sprite, 'hitbox', getattr(sprite, 'rect', None))``,
# preferring a ``hitbox`` attribute (which carries the entity's precise
# hurtbox) and falling back to the sprite's coarse ``rect`` for terrain
# tiles.  Both protocols are accepted at insertion so tiles and entities share
# one grid without adapter wrappers.
SpatialHashMember = SpatialHashable | RectHashable


class SpatialHash:
    """2D grid mapping each cell to the sprites overlapping it.

    This is particularly effective for tile-based games where most
    collision objects (tiles) are static and can be bucketed once at
    level load time, while the few dynamic ones are re-bucketed per tick.

    Attributes
    ----------
    cell_size : int
        Size of each grid cell in pixels. Larger cells = fewer cells
        but more sprites per cell. 128px is a good default for 64px tiles.
    grid : dict[tuple[int, int], list[SpatialHashMember]]
        Mapping of cell coordinates to lists of sprites in that cell.
    """

    def __init__(self, cell_size: int = 128):
        """Initialize the spatial hash with a cell size.

        Args:
            cell_size: Size of each grid cell in pixels. 128px (2x tile size)
                works well for 64px tiles.
        """
        self.cell_size = cell_size
        self.grid: dict[tuple[int, int], list[SpatialHashMember]] = defaultdict(list)
        # Cells each registered sprite currently occupies (keyed by id()).
        self._cells_by_sprite: dict[int, tuple[tuple[int, int], ...]] = {}

    def add(self, sprite: SpatialHashMember) -> None:
        """Register a sprite in every cell its hitbox overlaps (idempotent).

        Args:
            sprite: A sprite with a hitbox or rect to add to the grid.
        """
        box = self._box_of(sprite)
        if box is None:
            return  # Skip sprites without hitbox or rect
        key = id(sprite)
        if key in self._cells_by_sprite:
            return
        cells = self._cells_for_box(box)
        for cell in cells:
            self.grid[cell].append(sprite)
        self._cells_by_sprite[key] = cells

    def add_all(self, sprites: Iterable[SpatialHashMember]) -> None:
        """Register multiple sprites.

        Args:
            sprites: Iterable of sprites to add.
        """
        for sprite in sprites:
            self.add(sprite)

    def remove(self, sprite: SpatialHashMember) -> None:
        """Unregister a sprite from every cell it occupies.

        Args:
            sprite: The sprite previously registered via ``add``.
        """
        cells = self._cells_by_sprite.pop(id(sprite), None)
        if cells is None:
            return
        for cell in cells:
            bucket = self.grid.get(cell)
            if bucket is None:
                continue
            try:
                bucket.remove(sprite)
            except ValueError:
                pass
            if not bucket:
                del self.grid[cell]

    def update(self, sprite: SpatialHashMember) -> None:
        """Re-bucket a sprite after its hitbox moved.

        Args:
            sprite: A registered sprite whose hitbox changed position.
        """
        self.remove(sprite)
        self.add(sprite)

    def update_all(self, sprites: Iterable[SpatialHashMember]) -> None:
        """Re-bucket multiple sprites (e.g. moving platforms each tick).

        Args:
            sprites: Iterable of registered sprites that moved this tick.
        """
        for sprite in sprites:
            self.update(sprite)

    def clear(self) -> None:
        """Remove all sprites from the grid."""
        self.grid.clear()
        self._cells_by_sprite.clear()

    def get_nearby(self, hitbox: pygame.Rect | pygame.FRect) -> list[SpatialHashMember]:
        """Return the sprites overlapping the cells covered by ``hitbox``.

        The cell range is computed from the hitbox inflated by
        ``QUERY_MARGIN_PX`` on every side, so sprites resting on a surface or
        reached during this tick's substeps are never missed. Sprites
        spanning several cells are returned once. Callers still perform the
        real collision test on the returned candidates.

        Args:
            hitbox: The hitbox to query around.

        Returns:
            List of sprites that might collide. May include false positives.
        """
        margin = QUERY_MARGIN_PX
        query = pygame.FRect(
            hitbox.left - margin,
            hitbox.top - margin,
            hitbox.width + 2 * margin,
            hitbox.height + 2 * margin,
        )
        nearby: list[SpatialHashMember] = []
        seen: set[int] = set()
        for cell in self._cells_for_box(query):
            for sprite in self.grid.get(cell, ()):
                key = id(sprite)
                if key not in seen:
                    seen.add(key)
                    nearby.append(sprite)
        return nearby

    @staticmethod
    def _box_of(sprite: SpatialHashMember) -> pygame.Rect | pygame.FRect | None:
        """Return a sprite's hitbox, falling back to its rect."""
        return getattr(sprite, "hitbox", getattr(sprite, "rect", None))

    def _cells_for_box(
        self, box: pygame.Rect | pygame.FRect
    ) -> tuple[tuple[int, int], ...]:
        """Return every cell the box overlaps, column-major.

        Args:
            box: A pygame Rect or FRect.

        Returns:
            Tuple of (cell_x, cell_y) coordinates for each covered cell.
        """
        x0 = floor(box.left / self.cell_size)
        x1 = ceil(box.right / self.cell_size) - 1
        y0 = floor(box.top / self.cell_size)
        y1 = ceil(box.bottom / self.cell_size) - 1
        if x1 < x0:  # zero-width box: keep a single column
            x1 = x0
        if y1 < y0:  # zero-height box: keep a single row
            y1 = y0
        return tuple(
            (cx, cy) for cy in range(y0, y1 + 1) for cx in range(x0, x1 + 1)
        )
