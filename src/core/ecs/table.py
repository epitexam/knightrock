"""Dense component storage keyed by an id and a generation.

An entity id alone is not enough once rows are recycled: a stale reference to
a released projectile must not silently address the projectile that reused its
slot. A ``Handle`` is therefore ``(id, generation)``; releasing a slot bumps the
generation, and the old handle can never resolve again.

This module owns identity and storage only. It has no dependency on entities,
projectiles, pygame or the simulation, so it can be built and tested before any
caller moves over to it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

type Handle = tuple[str, int]

__all__ = ["Handle", "DenseTable"]


class DenseTable:
    """Parallel columns addressed by dense slots, with generation-checked keys."""

    def __init__(self, columns: Iterable[str] = ()) -> None:
        self._slot_of: dict[Handle, int] = {}
        self._handle_at: list[Handle] = []
        self._free: list[int] = []
        self._defaults: dict[str, Any] = dict.fromkeys(columns)
        self._columns: dict[str, list[Any]] = {name: [] for name in columns}
        self.alive: list[int] = []

    def add_column(self, name: str, default: Any = None) -> None:
        """Add a column, backfilling the rows that already exist."""
        if name in self._columns:
            raise ValueError(f"duplicate column {name!r}")
        self._defaults[name] = default
        self._columns[name] = [default for _ in self._handle_at]

    def column(self, name: str) -> list[Any]:
        """The backing list of one column, for systems that iterate it."""
        return self._columns[name]

    def acquire(self, handle: Handle) -> int:
        """Reserve a slot for a never-before-seen handle."""
        if handle in self._slot_of:
            raise ValueError(f"handle {handle!r} is already live")
        if self._free:
            slot = self._free.pop()
            self._handle_at[slot] = handle
            for name, values in self._columns.items():
                values[slot] = self._defaults[name]
        else:
            slot = len(self._handle_at)
            self._handle_at.append(handle)
            for values in self._columns.values():
                values.append(None)
        self._slot_of[handle] = slot
        self.alive.append(slot)
        return slot

    def release(self, slot: int) -> Handle:
        """Free a slot and return the handle that just died (with its generation)."""
        handle = self._handle_at[slot]
        del self._slot_of[handle]
        self._handle_at[slot] = (handle[0], handle[1] + 1)
        self._free.append(slot)
        self.alive.remove(slot)
        return handle

    def slot_of(self, handle: Handle) -> int | None:
        """The live slot for ``handle``, or ``None`` if it was released."""
        return self._slot_of.get(handle)

    def handle_at(self, slot: int) -> Handle:
        """The current handle of a slot, including its generation."""
        return self._handle_at[slot]

    def __len__(self) -> int:
        return len(self.alive)
