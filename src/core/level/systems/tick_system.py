"""TickSystem: bookkeeping tail of the level pipeline (audit F1.2, Phase 3 #2).

Runs last, after every simulation and notification stage: records the
end-of-tick rollback snapshot, then advances the monotonic tick counter.
The snapshot is recorded even when hit-stop suspended the simulation (the
hit-stop timer itself advances every tick), so ``rollback_to(tick)``
restores the exact end-of-tick world state.
"""

from typing import TYPE_CHECKING, Protocol

from src.core.rollback.snapshots import LevelSnapshot

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from src.core.rollback import RollbackSystem

__all__ = ["TickSystem", "TickOwner"]


class TickOwner(Protocol):
    """Narrow view of the level the tick stage bookkeeps through."""

    tick: int
    rollback_enabled: bool

    def save_state(self) -> LevelSnapshot: ...


class TickSystem:
    """Record the rollback snapshot, then advance the tick counter."""

    def process(self, level: TickOwner, rollback: RollbackSystem) -> None:
        """Capture the tick, then advance the level's counter by one."""
        if level.rollback_enabled:
            # ``Level`` satisfies ``TickOwner`` structurally (tick counter,
            # opt-in flag, snapshot hook); the protocol keeps the stage
            # testable without importing the level aggregate.
            rollback.record(level)  # type: ignore[arg-type]
        level.tick += 1
