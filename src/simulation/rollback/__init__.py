"""Local rollback core (audit Phase 3 #3).

Wires the snapshot primitives that already existed in the combat layer
(``CombatSnapshot``/``AttackStateSnapshot``/``ChargeSnapshot``) into a
working, testable ring buffer that can rewind a whole ``Level`` tick by
tick.  Transport and remote reconciliation remain future work.
"""

from src.simulation.rollback.rollback import RollbackSystem
from src.simulation.rollback.snapshots import LevelSnapshot, PlatformSnapshot, ProjectileSnapshot

__all__ = ["LevelSnapshot", "PlatformSnapshot", "ProjectileSnapshot", "RollbackSystem"]
