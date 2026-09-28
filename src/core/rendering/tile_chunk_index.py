"""Spatial index over the level's frozen tile planes.

Why this exists
---------------
The world draw used to camera-cull *every* sprite in the level, on every
frame: about 970 terrain tiles were tested against the viewport sixty times a
second to find the ~90 that were on screen. Measured on the registered level
at 1280x720, that single loop was 0.63 ms of ``Camera.is_visible`` plus
0.42 ms of loop body per frame -- two thirds of the 1.22 ms world draw -- and
91 % of the work it did was thrown away.

    The terrain does not move. It is built once when the level loads and stays
    put for the whole session, which is exactly the property a spatial index
    exploits and the property nothing else on the draw path has.

How it works
------------
Tiles are bucketed into square chunks of :data:`CHUNK_TILES` tiles. A lookup
takes the chunks the viewport overlaps and returns their sprites.


Two properties make the result *exactly* the old one, not merely close:

- **Chunks are a conservative superset.** A sprite is registered in every
  chunk its rectangle touches, and the lookup returns every sprite in every
  chunk the viewport touches. A sprite visible in the viewport therefore
  always overlaps at least one chunk the viewport overlaps, so it is always
  a candidate. The caller still runs the precise
  :meth:`~src.core.rendering.camera.Camera.is_visible` test on the
  candidates; the index only decides which sprites are worth asking about.
  A sprite straddling several chunks appears in several chunk lists, so the
  lookup deduplicates.
- **Build order is preserved.** Sprites come back in the order they went in,
  because the draw order of a tile plane is its Tiled layer order and
  reordering it would put a background layer over the terrain. Chunk lists
  are appended in ascending order, so sorting the gathered indices restores
  the original order; and because each list is already sorted, that sort is a
  merge of a handful of runs rather than a general sort.

Only frozen sprites belong in here. A sprite that moves after the index is
built is registered where it *was*, and will be culled against a stale
rectangle.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import pygame

from src.core.settings import World

CHUNK_TILES = 4
"""Tiles per chunk side.

Sized against the framing, which is the only thing that decides how many
chunks a frame has to touch. The framing is 1152x648 world units and a tile
is 64, so a frame looks at 18x10 tiles; a 4-tile chunk puts that at 5x3
chunks, and the padded query touches about 30 of them.

Smaller chunks select fewer candidates -- a 1-tile chunk is exact, since the
candidate set becomes the visible set -- but each one costs another dict
lookup and another position to merge, and at 1 tile the bookkeeping costs more
than the culling it saves (measured: 0.035 ms per lookup versus 0.011 ms at
4 tiles, against a cull that only gets 0.05 ms cheaper). Larger chunks go the
other way: 16 tiles is the whole level in three buckets for this framing, so a
query returns two thirds of the terrain and the index degenerates into the
scan it replaced.

The value is a rendering detail, not a gameplay one: it changes which sprites
are *asked about*, never which are drawn. ``render_benchmark.py`` measures the
trade-off at several sizes.
"""

ChunkKey = tuple[int, int]
"""Chunk coordinates, in chunk units (not tiles, not pixels)."""


class TileChunkIndex:
    """A frozen spatial index over a plane of static sprites.

    Parameters
    ----------
    sprites:
        The plane to index, in draw order. The iteration order is recorded and
        restored by :meth:`candidates`, so it is load-bearing.
    tile_size:
        World units per tile. Defaults to the world setting; only tests that
        build a synthetic plane need to say otherwise.
    chunk_tiles:
        Tiles per chunk side.
    """

    def __init__(
        self,
        sprites: Iterable[pygame.sprite.Sprite],
        *,
        tile_size: float = World.TILE_SIZE,
        chunk_tiles: int = CHUNK_TILES,
    ) -> None:
        if tile_size <= 0.0:
            raise ValueError(f"A chunk index needs a positive tile size, got {tile_size!r}")
        if chunk_tiles < 1:
            raise ValueError(f"A chunk needs at least one tile per side, got {chunk_tiles!r}")
        self._chunk_span = tile_size * chunk_tiles
        self._ordered: tuple[pygame.sprite.Sprite, ...] = tuple(sprites)
        self._owned_ids: frozenset[int] = frozenset(id(sprite) for sprite in self._ordered)
        self._chunks: dict[ChunkKey, list[int]] = {}
        # Sprites with no rectangle cannot be placed in a chunk, so they are
        # returned unconditionally rather than silently dropped. The linear
        # draw path treats a missing rect as an empty one; matching that here
        # is what keeps the two paths equivalent.
        self._unplaceable: tuple[int, ...] = ()
        unplaceable: list[int] = []
        for position, sprite in enumerate(self._ordered):
            keys = self._chunk_keys_for(sprite)
            if keys is None:
                unplaceable.append(position)
                continue
            for key in keys:
                self._chunks.setdefault(key, []).append(position)
        self._unplaceable = tuple(unplaceable)

    def _chunk_keys_for(self, sprite: pygame.sprite.Sprite) -> list[ChunkKey] | None:
        """Every chunk the sprite's rectangle touches, or None if unplaceable."""
        rect = sprite.rect
        if rect is None:
            return None
        span = self._chunk_span
        # ``floor`` on both ends, so a sprite straddling a chunk border is
        # registered on both sides and a negative coordinate lands in the chunk
        # below the origin instead of being truncated towards zero.
        left = math.floor(rect.left / span)
        right = math.floor((rect.right - 1) / span)
        top = math.floor(rect.top / span)
        bottom = math.floor((rect.bottom - 1) / span)
        return [
            (column, row) for column in range(left, right + 1) for row in range(top, bottom + 1)
        ]

    def candidates(self, viewport: pygame.FRect) -> list[pygame.sprite.Sprite]:
        """Sprites that may intersect ``viewport``, in build order.

        A superset of the visible sprites, never a subset: the caller is still
        responsible for the exact test.
        """
        positions: set[int] = set(self._unplaceable)
        for key in self._viewport_keys(viewport):
            positions.update(self._chunks.get(key, ()))
        if not positions:
            return []
        ordered_positions = sorted(positions)
        ordered = self._ordered
        return [ordered[position] for position in ordered_positions]

    def _viewport_keys(self, viewport: pygame.FRect) -> list[ChunkKey]:
        """Chunks the viewport rectangle touches.

        Padded by one chunk on the right and below. ``rect.right - 1`` is
        correct for a rectangle that ends exactly on a chunk border, but a
        viewport whose origin is fractional (the camera interpolates) would
        otherwise skip the chunk its right edge is inside.
        """
        span = self._chunk_span
        left = math.floor(viewport.left / span)
        right = math.floor(viewport.right / span)
        top = math.floor(viewport.top / span)
        bottom = math.floor(viewport.bottom / span)
        return [
            (column, row) for column in range(left, right + 1) for row in range(top, bottom + 1)
        ]

    def owns(self, sprite: pygame.sprite.Sprite) -> bool:
        """Whether ``sprite`` is drawn through this index rather than the scan.

        Keyed by ``id`` because that is all the draw path needs, and it is
        safe here: the index holds a strong reference to every sprite it owns
        for as long as it lives, so no owned id can be recycled onto a
        different object and hand a sprite the wrong answer.
        """
        return id(sprite) in self._owned_ids

    def __len__(self) -> int:
        return len(self._ordered)
