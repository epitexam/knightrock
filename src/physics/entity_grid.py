"""Entity spatial hash — the PERF-02 follow-up to the environment grid.

``SpatialHash`` buckets the *environment* (tiles, moving platforms). The
entity-pairing systems (separation, contact damage, combat hit detection)
used to test every pair exhaustively — O(n²) per tick.  This module adds
the missing half: a grid over the **entities themselves**, rebuilt in one
O(n) pass at the start of every tick, so each system only tests pairs that
are actually near each other (O(n · k), k = neighbours per entity).

Determinism
-----------
Rebuilding from scratch each tick keeps the grid exact: no stale buckets,
no incremental bookkeeping to get wrong after a push moves two entities.
``overlapping_pairs`` also preserves the *pair order* of the legacy
exhaustive loops ((i, j) with i < j in insertion order, candidates sorted
by index), so simulation results stay bit-identical with and without the
grid — the grid can only remove pairs that could never overlap.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any, cast

import pygame

from src.physics.spatial_hash import SpatialHash, SpatialHashMember

__all__ = ["EntityGrid", "overlapping_pairs"]


class EntityGrid:
    """Per-tick spatial hash over the live entities.

    The grid is deliberately rebuilt from scratch each tick (``rebuild``)
    instead of being updated incrementally: entity positions all change
    every tick, so a full rebuild costs the same O(n) as the incremental
    bookkeeping while never leaving a stale bucket behind.

    Attributes
    ----------
    cell_size : int
        Grid cell edge, shared with the environment hash (128 px).
    """

    def __init__(self, cell_size: int = 128) -> None:
        self.cell_size = cell_size
        self._hash = SpatialHash(cell_size=cell_size)

    def rebuild(self, entities: Iterable[Any]) -> int:
        """Re-bucket every entity in one pass; return the member count.

        Args:
            entities: The live entities, typically
                ``groups.entity_sprites``. Anything exposing ``hitbox`` or
                ``rect`` qualifies (pygame Sprite subclasses do at runtime;
                the static ``Sprite`` type simply doesn't declare them).
        """
        self._hash.clear()
        count = 0
        for entity in entities:
            self._hash.add(entity)
            count += 1
        return count

    def near(self, box: pygame.Rect | pygame.FRect) -> list[SpatialHashMember]:
        """Return the entities that may overlap ``box`` (false positives OK).

        Delegates to :meth:`SpatialHash.get_nearby`, which inflates the
        query by ``QUERY_MARGIN_PX`` — a separation push of a few pixels
        between the rebuild and the query can therefore never hide a real
        neighbour.
        """
        return self._hash.get_nearby(box)

    def append_near(
        self,
        box: pygame.Rect | pygame.FRect,
        nearby: list[SpatialHashMember],
        seen: set[int],
    ) -> None:
        """Append grid members into caller-owned buffers."""
        self._hash.append_nearby(box, nearby, seen)

    def clear(self) -> None:
        """Empty the grid (level teardown)."""
        self._hash.clear()


def overlapping_pairs(entities: Sequence[Any], grid: EntityGrid) -> Iterator[tuple[Any, Any]]:
    """Yield every overlapping entity pair, in legacy exhaustive-loop order.

    Replacement for the ``for i / for j > i`` double loop of the pairing
    systems: candidates are pruned through ``grid`` (only near neighbours
    are tested) but the pair order is preserved — for each ``i``, partners
    are yielded by ascending index ``j > i``.  Simulation behaviour is
    therefore identical to the exhaustive version, at O(n · k) instead of
    O(n²).

    Args:
        entities: The filtered entity list, in insertion order.
        grid: The per-tick :class:`EntityGrid` covering (a superset of)
            these entities.

    Yields:
        ``(ent_a, ent_b)`` pairs whose hitboxes truly overlap.
    """
    position = {id(entity): index for index, entity in enumerate(entities)}
    for index_a, ent_a in enumerate(entities):
        candidates: list[tuple[int, Any]] = []
        # Grid members outside `entities` (the grid may bucket a superset,
        # e.g. the whole entity group while the caller filtered it) sort to
        # index -1 and are dropped by the `index_b <= index_a` guard.
        members = cast(list[Any], grid.near(ent_a.hitbox))
        for ent_b in members:
            index_b = position.get(id(ent_b), -1)
            if index_b <= index_a:
                continue
            if not ent_a.hitbox.colliderect(ent_b.hitbox):
                continue
            candidates.append((index_b, ent_b))
        candidates.sort(key=lambda pair: pair[0])
        for _, ent_b in candidates:
            yield ent_a, ent_b
