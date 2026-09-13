"""Ring buffer of level tick snapshots with deterministic restore.

This is the *local* half of the netcode-ready rollback machinery whose
snapshot primitives the codebase already carried (``CombatSnapshot``,
``AttackStateSnapshot``, ``ChargeSnapshot`` — audit F2.5 / Phase 3 #3).
A ``RollbackSystem`` records a ``LevelSnapshot`` at the end of every fixed
tick into a bounded ``deque`` and can rewind the level to any still-buffered
tick.

Resurrection and reaping
------------------------
Restoring a snapshot also repairs the live sprite groups:

- an entity that has since been ``kill()``-ed is re-added to the groups it
  belonged to at capture time (recorded on :class:`EntitySnapshot.groups`);
- an entity spawned *after* the target tick (e.g. debug spawn) is reaped,
  because it must not exist in the restored simulation.

The transport layer (network, input replay, remote reconciliation) is out of
scope here — this module only makes the simulation rewinding real and testable.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from src.core.rollback.snapshots import LevelSnapshot
from src.core.settings import Simulation

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from src.core.level.level import Level

__all__ = ["RollbackSystem"]


class RollbackSystem:
    """Record per-tick snapshots and rewind the owning level on demand.

    Parameters
    ----------
    capacity : int
        Number of ticks kept in the ring buffer.  Defaults to
        ``Simulation.MAX_PREDICTION_FRAMES`` — the deepest rollback a
        prediction window can ever require.
    """

    def __init__(self, capacity: int = Simulation.MAX_PREDICTION_FRAMES) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._buffer: deque[LevelSnapshot] = deque(maxlen=capacity)

    def __len__(self) -> int:
        """Number of buffered snapshots."""
        return len(self._buffer)

    @property
    def oldest_tick(self) -> int | None:
        """Oldest bufferable tick, or ``None`` when empty."""
        return self._buffer[0].tick if self._buffer else None

    @property
    def latest_tick(self) -> int | None:
        """Most recent bufferable tick, or ``None`` when empty."""
        return self._buffer[-1].tick if self._buffer else None

    def record(self, level: Level) -> None:
        """Capture the level's current state and push it onto the buffer."""
        self._buffer.append(level.save_state())

    def can_rollback_to(self, tick: int) -> bool:
        """Whether ``tick`` is still buffered."""
        return self.oldest_tick is not None and self.oldest_tick <= tick <= (self.latest_tick or 0)

    def rollback_to(self, level: Level, tick: int) -> bool:
        """Rewind the level to ``tick``; returns ``False`` if it is evicted.

        On success, snapshots newer than ``tick`` are dropped — the future is
        being re-simulated, so those frames are stale.
        """
        snapshot = self._find(tick)
        if snapshot is None:
            return False

        level.load_state(snapshot)

        while self._buffer and self._buffer[-1].tick > tick:
            self._buffer.pop()
        return True

    def clear(self) -> None:
        """Empty the buffer (level teardown)."""
        self._buffer.clear()

    def _find(self, tick: int) -> LevelSnapshot | None:
        for snapshot in self._buffer:
            if snapshot.tick == tick:
                return snapshot
        return None