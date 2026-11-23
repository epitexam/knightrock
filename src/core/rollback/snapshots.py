"""Level-wide snapshots for the local rollback core (audit Phase 3 #3).

These dataclasses group the per-entity ``EntitySnapshot`` s (from
``src.entities.entity``) together with the level's own transient gameplay
state — respawn/death counters, exit flag, the global hit-stop timer, and
the moving-platform kinematics — so a whole tick can be captured and
restored bit-exactly.

A ``LevelSnapshot`` is *local*: it stores live entity/platform references
so ``RollbackSystem`` can resurrect killed sprites and re-add them to their
groups.  The scalar fields are the serializable part a network rollback
would transmit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from src.combat.shapes import ShapePose
from src.core.ecs.table import Handle
from src.core.input.input_state import InputState
from src.entities.entity import EntitySnapshot
from src.entities.projectile import Projectile, ProjectileConfig


class SnapshotCapable(Protocol):
    """Anything ``RollbackSystem.record`` can capture: ``save_state`` only."""

    def save_state(self) -> LevelSnapshot: ...


@dataclass(frozen=True)
class PlatformSnapshot:
    """Capture of one moving platform's kinematic state."""

    platform: Any
    pos: tuple[float, float]
    current_target: int
    direction: int


@dataclass(frozen=True)
class ProjectileSnapshot:
    """Capture of one in-flight projectile's changing state.

    ``projectile`` is a live reference so a rewind can re-add it to its groups,
    just like ``EntitySnapshot.entity``. The swept-shape origins are derived at
    the next tick and are not captured.
    """

    projectile: Projectile
    id: str
    pos: tuple[float, float]
    velocity: tuple[float, float]
    life: float
    active: bool
    is_dead: bool
    faction: str
    facing_right: bool
    config: ProjectileConfig
    contact_shape: ShapePose
    targets_hit: frozenset[str]
    #: Generation-checked identity of the dense row this shot came from.
    handle: Handle


@dataclass
class LevelSnapshot:
    """Capture of a level's full simulation state at one tick."""

    tick: int
    hit_stop_timer: float
    respawn_timer: float
    deaths: int
    exit_reached: bool
    player_dead_emitted: bool
    completed_emitted: bool
    input_current: InputState = field(default_factory=InputState)
    input_previous: InputState = field(default_factory=InputState)
    entities: dict[str, EntitySnapshot] = field(default_factory=dict)
    platforms: list[PlatformSnapshot] = field(default_factory=list)
    projectiles: list[ProjectileSnapshot] = field(default_factory=list)
