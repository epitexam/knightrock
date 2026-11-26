"""Backward-compatible path for :mod:`src.simulation.entities.entity`."""

from src.simulation.entities.entity import (
    FACING_LOCKED as FACING_LOCKED,
)
from src.simulation.entities.entity import (
    AnimationPublisher as AnimationPublisher,
)
from src.simulation.entities.entity import (
    Animator as Animator,
)
from src.simulation.entities.entity import (
    Any as Any,
)
from src.simulation.entities.entity import (
    AttackDefinition as AttackDefinition,
)
from src.simulation.entities.entity import (
    ClashSettings as ClashSettings,
)
from src.simulation.entities.entity import (
    CollisionSprite as CollisionSprite,
)
from src.simulation.entities.entity import (
    Combatant as Combatant,
)
from src.simulation.entities.entity import (
    CombatComponent as CombatComponent,
)
from src.simulation.entities.entity import (
    CombatSettings as CombatSettings,
)
from src.simulation.entities.entity import (
    CombatSnapshot as CombatSnapshot,
)
from src.simulation.entities.entity import (
    CombatTable as CombatTable,
)
from src.simulation.entities.entity import (
    DamageResult as DamageResult,
)
from src.simulation.entities.entity import (
    DamageType as DamageType,
)
from src.simulation.entities.entity import (
    DashController as DashController,
)
from src.simulation.entities.entity import (
    DoomTracker as DoomTracker,
)
from src.simulation.entities.entity import (
    Entity as Entity,
)
from src.simulation.entities.entity import (
    EntitySnapshot as EntitySnapshot,
)
from src.simulation.entities.entity import (
    EnvironmentScanner as EnvironmentScanner,
)
from src.simulation.entities.entity import (
    Finish as Finish,
)
from src.simulation.entities.entity import (
    GeometryTable as GeometryTable,
)
from src.simulation.entities.entity import (
    Group as Group,
)
from src.simulation.entities.entity import (
    Height as Height,
)
from src.simulation.entities.entity import (
    HitFlash as HitFlash,
)
from src.simulation.entities.entity import (
    HurtboxZoneDef as HurtboxZoneDef,
)
from src.simulation.entities.entity import (
    IdFactory as IdFactory,
)
from src.simulation.entities.entity import (
    Iterable as Iterable,
)
from src.simulation.entities.entity import (
    KnockbackConfig as KnockbackConfig,
)
from src.simulation.entities.entity import (
    Literal as Literal,
)
from src.simulation.entities.entity import (
    Locomotion as Locomotion,
)
from src.simulation.entities.entity import (
    Mapping as Mapping,
)
from src.simulation.entities.entity import (
    MoveId as MoveId,
)
from src.simulation.entities.entity import (
    MovementComponent as MovementComponent,
)
from src.simulation.entities.entity import (
    MovementTable as MovementTable,
)
from src.simulation.entities.entity import (
    NullCombatComponent as NullCombatComponent,
)
from src.simulation.entities.entity import (
    NullStateMachine as NullStateMachine,
)
from src.simulation.entities.entity import (
    Physics as Physics,
)
from src.simulation.entities.entity import (
    PresentationSprite as PresentationSprite,
)
from src.simulation.entities.entity import (
    ReactionComponent as ReactionComponent,
)
from src.simulation.entities.entity import (
    ReactionStatus as ReactionStatus,
)
from src.simulation.entities.entity import (
    RenderHints as RenderHints,
)
from src.simulation.entities.entity import (
    Sequence as Sequence,
)
from src.simulation.entities.entity import (
    ShapeKind as ShapeKind,
)
from src.simulation.entities.entity import (
    ShapePose as ShapePose,
)
from src.simulation.entities.entity import (
    SpatialHash as SpatialHash,
)
from src.simulation.entities.entity import (
    SpriteGroups as SpriteGroups,
)
from src.simulation.entities.entity import (
    Stance as Stance,
)
from src.simulation.entities.entity import (
    StateMachine as StateMachine,
)
from src.simulation.entities.entity import (
    StateMachineSnapshot as StateMachineSnapshot,
)
from src.simulation.entities.entity import (
    StunSettings as StunSettings,
)
from src.simulation.entities.entity import (
    SweptShape as SweptShape,
)
from src.simulation.entities.entity import (
    Turn as Turn,
)
from src.simulation.entities.entity import (
    Vector2 as Vector2,
)
from src.simulation.entities.entity import (
    Vitals as Vitals,
)
from src.simulation.entities.entity import (
    VitalsSnapshot as VitalsSnapshot,
)
from src.simulation.entities.entity import (
    VitalsTable as VitalsTable,
)
from src.simulation.entities.entity import (
    WallJumpLock as WallJumpLock,
)
from src.simulation.entities.entity import (
    __all__ as __all__,
)
from src.simulation.entities.entity import (
    apply_horizontal_movement as apply_horizontal_movement,
)
from src.simulation.entities.entity import (
    apply_moving_platform as apply_moving_platform,
)
from src.simulation.entities.entity import (
    cast as cast,
)
from src.simulation.entities.entity import (
    dataclass as dataclass,
)
from src.simulation.entities.entity import (
    field as field,
)
from src.simulation.entities.entity import (
    load_attacks as load_attacks,
)
from src.simulation.entities.entity import (
    move_entity as move_entity,
)
from src.simulation.entities.entity import (
    pygame as pygame,
)
from src.simulation.entities.entity import (
    random as random,
)
from src.simulation.entities.entity import (
    resolve_collisions as resolve_collisions,
)
from src.simulation.entities.entity import (
    resolve_turn_profile as resolve_turn_profile,
)
from src.simulation.entities.entity import (
    shared_id_factory as shared_id_factory,
)
from src.simulation.entities.entity import (
    state_names as state_names,
)
from src.simulation.entities.entity import (
    swept_box as swept_box,
)
