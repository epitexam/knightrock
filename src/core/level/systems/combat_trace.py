"""Per-tick combat contact dump (Axe G, hitbox_amelioration.md).

Records one :class:`HitCandidate` per landed contact (and per tick summary)
into a bounded ring buffer, optionally flushed as JSON lines for replaying a
suspicious whiff. Off by default: enabled only when ``DEBUG=1`` *and*
``DEBUG_COMBAT_DUMP=1``, with an early return before any allocation so the
hot path stays allocation-free in normal runs (bench 2.2).
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from src.core.settings import Debug

__all__ = ["CombatTrace", "HitCandidate"]


@dataclass(frozen=True)
class HitCandidate:
    """One recorded contact candidate for the dump (Axe G)."""

    tick: int
    kind: str
    owner_id: str
    target_id: str
    box_count: int
    zone_index: int
    zone_mult: float
    pairs_tested: int
    overlaps: int
    contacts: int
    guarded: bool
    damage: float


class CombatTrace:
    """Bounded ring of :class:`HitCandidate` with optional JSONL flush.

    Parameters
    ----------
    enabled:
        When false, :meth:`record` returns before touching the buffer.
    maxlen:
        Ring capacity (pattern ``RollbackSystem``); oldest entries drop.
    """

    def __init__(self, enabled: bool = False, maxlen: int = 256) -> None:
        self.enabled = enabled
        self._buffer: deque[HitCandidate] = deque(maxlen=maxlen)
        self._tick = 0

    @staticmethod
    def is_enabled() -> bool:
        """Debug overlay on *and* explicit dump opt-in via env."""
        return Debug.is_enabled() and os.getenv("DEBUG_COMBAT_DUMP", "0") == "1"

    @property
    def tick(self) -> int:
        return self._tick

    def begin_tick(self) -> None:
        """Advance the monotonic tick counter (called once per sim tick)."""
        self._tick += 1

    def record(self, candidate: HitCandidate) -> None:
        """Append one candidate; no-op (and no allocation of buffer slots)
        when the trace is disabled."""
        if not self.enabled:
            return
        self._buffer.append(candidate)

    def __len__(self) -> int:
        return len(self._buffer)

    def drain_jsonl(self, path: Path) -> Path:
        """Write every buffered candidate as one JSON object per line, then clear.

        Creates parent directories as needed. Returns the written path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for candidate in self._buffer:
                handle.write(json.dumps(asdict(candidate), sort_keys=True) + "\n")
        self._buffer.clear()
        return path
