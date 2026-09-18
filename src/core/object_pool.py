"""Generic object pool (audit F6.3, Phase 3 #1).

Projectiles, particles and other short-lived objects are created and
destroyed by the hundreds per second; CPython allocation + GC churn is the
next bottleneck once entity counts grow.  :class:`ObjectPool` keeps a free
list so ``acquire`` reuses a dead instance (after an optional ``reset``)
instead of building a new one, and ``release`` parks instances back.

The pool is deliberately minimal: no threads, no weakrefs, no max-size —
the gameplay wiring (projectiles, particles) will add its own caps.  It is
a building block of Phase 3 #1, unused by the simulation yet.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")

__all__ = ["ObjectPool"]


class ObjectPool(Generic[T]):
    """Recycle expensive-to-create objects through a free list.

    Parameters
    ----------
    factory : Callable[[], T]
        Builds a brand-new instance when the free list is empty.
    reset : Callable[[T], None] | None
        Runs on every recycled instance before it is handed out again
        (clear velocity, timers, flags...).  Never called on freshly
        created instances — the factory is expected to return a clean one.
    """

    def __init__(
        self,
        factory: Callable[[], T],
        reset: Callable[[T], None] | None = None,
    ) -> None:
        self._factory = factory
        self._reset = reset
        self._free: list[T] = []
        self._created = 0

    def acquire(self) -> T:
        """Take an instance from the pool, building one only if necessary."""
        if self._free:
            instance = self._free.pop()
            if self._reset is not None:
                self._reset(instance)
            return instance
        self._created += 1
        return self._factory()

    def release(self, instance: T) -> None:
        """Park ``instance`` back into the free list."""
        self._free.append(instance)

    def clear(self) -> None:
        """Drop every parked instance (they become garbage-collectable)."""
        self._free.clear()

    @property
    def available(self) -> int:
        """Instances parked and ready for reuse."""
        return len(self._free)

    @property
    def created(self) -> int:
        """Total instances ever built by the factory (reuse metric)."""
        return self._created
