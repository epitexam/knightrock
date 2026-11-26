"""Backward-compatible path for :mod:`src.simulation.data.attacks`."""

from src.simulation.data.attacks import (
    _ANCHOR_KINDS as _ANCHOR_KINDS,
)
from src.simulation.data.attacks import (
    _ATTACK_DEFAULTS as _ATTACK_DEFAULTS,
)
from src.simulation.data.attacks import (
    _DAMAGE_TYPES as _DAMAGE_TYPES,
)
from src.simulation.data.attacks import (
    _EASING_KINDS as _EASING_KINDS,
)
from src.simulation.data.attacks import (
    _HIT_DEFAULTS as _HIT_DEFAULTS,
)
from src.simulation.data.attacks import (
    _HITBOX_DEFAULTS as _HITBOX_DEFAULTS,
)
from src.simulation.data.attacks import (
    _KEYFRAME_DEFAULTS as _KEYFRAME_DEFAULTS,
)
from src.simulation.data.attacks import (
    _KNOCKBACK_DEFAULTS as _KNOCKBACK_DEFAULTS,
)
from src.simulation.data.attacks import (
    _KNOCKBACK_MODES as _KNOCKBACK_MODES,
)
from src.simulation.data.attacks import (
    _LEGACY_ANCHOR_KEY as _LEGACY_ANCHOR_KEY,
)
from src.simulation.data.attacks import (
    _LEGACY_HITBOX_FIELDS as _LEGACY_HITBOX_FIELDS,
)
from src.simulation.data.attacks import (
    _PHASE_DEFAULTS as _PHASE_DEFAULTS,
)
from src.simulation.data.attacks import (
    _PHASE_JSON_FIELDS as _PHASE_JSON_FIELDS,
)
from src.simulation.data.attacks import (
    _SHAPE_KINDS as _SHAPE_KINDS,
)
from src.simulation.data.attacks import (
    _STANCES as _STANCES,
)
from src.simulation.data.attacks import (
    ATTACKS_FILENAME as ATTACKS_FILENAME,
)
from src.simulation.data.attacks import (
    ATTACKS_VERSION as ATTACKS_VERSION,
)
from src.simulation.data.attacks import (
    MISSING as MISSING,
)
from src.simulation.data.attacks import (
    SUPPORTED_ATTACK_VERSIONS as SUPPORTED_ATTACK_VERSIONS,
)
from src.simulation.data.attacks import (
    AnchorKind as AnchorKind,
)
from src.simulation.data.attacks import (
    Any as Any,
)
from src.simulation.data.attacks import (
    AttackButton as AttackButton,
)
from src.simulation.data.attacks import (
    AttackDefinition as AttackDefinition,
)
from src.simulation.data.attacks import (
    Clash as Clash,
)
from src.simulation.data.attacks import (
    DamageType as DamageType,
)
from src.simulation.data.attacks import (
    EasingKind as EasingKind,
)
from src.simulation.data.attacks import (
    GameplayDataError as GameplayDataError,
)
from src.simulation.data.attacks import (
    Height as Height,
)
from src.simulation.data.attacks import (
    HitboxKeyframe as HitboxKeyframe,
)
from src.simulation.data.attacks import (
    HitboxSpec as HitboxSpec,
)
from src.simulation.data.attacks import (
    HitProperties as HitProperties,
)
from src.simulation.data.attacks import (
    KnockbackConfig as KnockbackConfig,
)
from src.simulation.data.attacks import (
    MoveId as MoveId,
)
from src.simulation.data.attacks import (
    Path as Path,
)
from src.simulation.data.attacks import (
    PhaseDefinition as PhaseDefinition,
)
from src.simulation.data.attacks import (
    ShapeKind as ShapeKind,
)
from src.simulation.data.attacks import (
    Stance as Stance,
)
from src.simulation.data.attacks import (
    StrEnum as StrEnum,
)
from src.simulation.data.attacks import (
    _defaults as _defaults,
)
from src.simulation.data.attacks import (
    _enum_value as _enum_value,
)
from src.simulation.data.attacks import (
    _field_names as _field_names,
)
from src.simulation.data.attacks import (
    _named as _named,
)
from src.simulation.data.attacks import (
    _pair_of_floats as _pair_of_floats,
)
from src.simulation.data.attacks import (
    _read_auto_into as _read_auto_into,
)
from src.simulation.data.attacks import (
    _read_extra_hitboxes as _read_extra_hitboxes,
)
from src.simulation.data.attacks import (
    _read_follow_ups as _read_follow_ups,
)
from src.simulation.data.attacks import (
    _read_hit as _read_hit,
)
from src.simulation.data.attacks import (
    _read_hitbox_keyframe as _read_hitbox_keyframe,
)
from src.simulation.data.attacks import (
    _read_hitbox_keyframes as _read_hitbox_keyframes,
)
from src.simulation.data.attacks import (
    _read_hitbox_spec as _read_hitbox_spec,
)
from src.simulation.data.attacks import (
    _read_hitboxes as _read_hitboxes,
)
from src.simulation.data.attacks import (
    _read_knockback as _read_knockback,
)
from src.simulation.data.attacks import (
    _read_launch as _read_launch,
)
from src.simulation.data.attacks import (
    _read_phase as _read_phase,
)
from src.simulation.data.attacks import (
    _read_stances as _read_stances,
)
from src.simulation.data.attacks import (
    _read_tags as _read_tags,
)
from src.simulation.data.attacks import (
    _required as _required,
)
from src.simulation.data.attacks import (
    annotations as annotations,
)
from src.simulation.data.attacks import (
    attack_definition_to_dict as attack_definition_to_dict,
)
from src.simulation.data.attacks import (
    attack_definition_to_v2_dict as attack_definition_to_v2_dict,
)
from src.simulation.data.attacks import (
    attacks_document as attacks_document,
)
from src.simulation.data.attacks import (
    cast as cast,
)
from src.simulation.data.attacks import (
    fields as fields,
)
from src.simulation.data.attacks import (
    read_attack_definition as read_attack_definition,
)
from src.simulation.data.attacks import (
    read_attacks_file as read_attacks_file,
)
from src.simulation.data.attacks import (
    read_bool as read_bool,
)
from src.simulation.data.attacks import (
    read_int as read_int,
)
from src.simulation.data.attacks import (
    read_json_object as read_json_object,
)
from src.simulation.data.attacks import (
    read_number as read_number,
)
from src.simulation.data.attacks import (
    reject_unknown as reject_unknown,
)
from src.simulation.data.attacks import (
    write_attacks_file as write_attacks_file,
)
