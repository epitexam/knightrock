"""Backward-compatible path for :mod:`src.simulation.combat.null_combat`."""

from src.simulation.combat.null_combat import (
    TYPE_CHECKING as TYPE_CHECKING,
)
from src.simulation.combat.null_combat import (
    AttackDefinition as AttackDefinition,
)
from src.simulation.combat.null_combat import (
    AttackStateSnapshot as AttackStateSnapshot,
)
from src.simulation.combat.null_combat import (
    ChargeSnapshot as ChargeSnapshot,
)
from src.simulation.combat.null_combat import (
    MoveId as MoveId,
)
from src.simulation.combat.null_combat import (
    NullCombatComponent as NullCombatComponent,
)
from src.simulation.combat.null_combat import (
    PhaseDefinition as PhaseDefinition,
)
from src.simulation.combat.null_combat import (
    PhaseState as PhaseState,
)
from src.simulation.combat.null_combat import (
    Refusal as Refusal,
)
from src.simulation.combat.null_combat import (
    ShapePose as ShapePose,
)
from src.simulation.combat.null_combat import (
    SweptShape as SweptShape,
)
from src.simulation.combat.null_combat import (
    _NullAttackState as _NullAttackState,
)
from src.simulation.combat.null_combat import (
    _NullChargeHandler as _NullChargeHandler,
)
from src.simulation.combat.null_combat import (
    _NullComboTracker as _NullComboTracker,
)
from src.simulation.combat.null_combat import (
    _NullHitboxManager as _NullHitboxManager,
)
from src.simulation.combat.null_combat import (
    annotations as annotations,
)
from src.simulation.combat.null_combat import (
    geometry_checksum as geometry_checksum,
)
from src.simulation.combat.null_combat import (
    pygame as pygame,
)
