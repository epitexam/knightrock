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

When the index is not worth building
-------------------------------------
A spatial index is a trade: pay to bucket, save by not testing pairs that are
far apart. Both halves are optional, and below a certain size neither pays.
``rebuild`` costs a hash insert per member and every query costs a cell walk
plus a dedupe, and for a handful of members that overhead exceeds the O(n²)
loop it replaces — measured at +0.011 ms per tick for a single entity, which
is most of what the whole broadphase costs at that size.

So :meth:`rebuild` decides whether to index at all, and the query methods
return every member when it decides not to. The bypass is a superset of what
the grid would have returned, and both consumers re-sort their candidates
into the caller's order, so **the pair sequence is identical either way** —
the choice is invisible in the simulation and only shows up in the timing.

Two conditions, and the second is the one that matters:

- fewer than :data:`MIN_GRID_MEMBERS` members, and
- the members do not span more than one cell. A population stacked in a
  single cell is a population the grid cannot prune: every query returns
  everything, and the only effect of indexing is the cost. That is the case
  the count threshold alone misses, and it is the *common* one — a tight
  melee is a handful of entities in one place, and the shipped level has
  exactly one entity in total.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any, cast

import pygame

from src.physics.spatial_hash import SpatialHash, SpatialHashMember

__all__ = ["MIN_GRID_MEMBERS", "EntityGrid", "overlapping_pairs"]

MIN_GRID_MEMBERS = 8
"""Below this many members, the grid is not queried and returns all of them.

See the module docstring: the measured crossover for a spread population is
around four members, and eight leaves room for a roving fight without giving
up the pruning that makes a crowded one affordable.
"""


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
    indexed : bool
        Whether the last :meth:`rebuild` decided the index was worth
        querying. False means the query methods answer with every member,
        which is the same set and cheaper at that size.
    """

    def __init__(self, cell_size: int = 128) -> None:
        self.cell_size = cell_size
        self._hash = SpatialHash(cell_size=cell_size)
        self._members: list[Any] = []
        self.indexed = False

    def rebuild(self, entities: Iterable[Any]) -> int:
        """Re-bucket every entity in one pass; return the member count.

        Bucketing is skipped outright when the count already rules the index
        out, so a level with a handful of entities pays one list copy per
        tick. Otherwise the cells are needed to make the second half of the
        decision, and :attr:`indexed` records whether the queries will use
        those buckets or short-circuit to the member list.

        Args:
            entities: The live entities, typically
                ``groups.entity_sprites``. Anything exposing ``hitbox`` or
                ``rect`` qualifies (pygame Sprite subclasses do at runtime;
                the static ``Sprite`` type simply doesn't declare them).
        """
        self._hash.clear()
        self._members = list(entities)
        if len(self._members) < MIN_GRID_MEMBERS:
            self.indexed = False
            return len(self._members)
        for entity in self._members:
            self._hash.add(entity)
        self.indexed = self._hash.occupied_cells > 1
        return len(self._members)

    def near(self, box: pygame.Rect | pygame.FRect) -> list[SpatialHashMember]:
        """Return the entities that may overlap ``box`` (false positives OK).

        Delegates to :meth:`SpatialHash.get_nearby`, which inflates the
        query by ``QUERY_MARGIN_PX` — a separation push of a few pixels
        between the rebuild and the query can therefore never hide a real
        neighbour. When the grid decided not to index, every member is
        returned instead: the same set, with nothing to prune.
        """
        if not self.indexed:
            return list(self._members)
        return self._hash.get_nearby(box)

    def append_near(
        self,
        box: pygame.Rect | pygame.FRect,
        nearby: list[SpatialHashMember],
        seen: set[int],
    ) -> None:
        """Append grid members into caller-owned buffers.

        The same bypass as :meth:`near`, honouring the caller's ``seen`` set
        so the result is identical to the indexed path's.
        """
        if not self.indexed:
            for member in self._members:
                key = id(member)
                if key not in seen:
                    seen.add(key)
                    nearby.append(member)
            return
        self._hash.append_nearby(box, nearby, seen)

    def clear(self) -> None:
        """Empty the grid (level teardown)."""
        self._hash.clear()
        self._members = []
        self.indexed = False


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
    # A grid that decided it was not worth indexing is walked exhaustively,
    # not queried. The two produce the same pairs in the same order, but the
    # query path also pays for a candidate sort per entity, which at a small
    # roster costs more than the pairs it is sorting.
    use_grid = grid.indexed
    for index_a, ent_a in enumerate(entities):
        candidates: list[tuple[int, Any]] = []
        # Grid members outside `entities` (the grid may bucket a superset,
        # e.g. the whole entity group while the caller filtered it) sort to
        # index -1 and are dropped by the `index_b <= index_a` guard.
        members = cast("list[Any]", grid.near(ent_a.hitbox)) if use_grid else list(entities)
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
