"""Typed JSON loader for attack frame data (Phase 3 #4).

``attacks.json`` groups attacks in named sets so each consumer only sees
its own moves::

    {"version": 1, "sets": {"player": {"light_attack": {...}, ...}, ...}}

Every structural field of ``AttackDefinition`` / ``PhaseDefinition`` /
``HitProperties`` is required in JSON except trailing documented tuning
defaults (``mode``, ``stagger``, flags, multipliers...), which are read from
the dataclass itself rather than restated here.  Unknown keys always raise, at
every level: a typo must fail loudly, never silently use a default.  An attack
set may carry ``"_comment"``-style keys, which are dropped.

Phases accept two hitbox dialects. The original spelling puts one primary box on
the phase (``hitbox_size`` / ``hitbox_offset``, plus ``hitbox_shape`` and
friends); the current one puts every box in a ``hitboxes`` list, each carrying
its own shape, angle, easing and anchor. Mixing the two is refused, and the
refusal names the offending keys rather than just saying they conflict.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

from src.combat.damage_types import DamageType
from src.combat.frame_data import (
    AttackDefinition,
    HitboxKeyframe,
    HitboxSpec,
    HitProperties,
    PhaseDefinition,
)
from src.combat.knockback import KnockbackConfig
from src.combat.shapes import AnchorKind, EasingKind, ShapeKind
from src.data.errors import GameplayDataError, read_json_object

ATTACKS_FILENAME = "attacks.json"
ATTACKS_VERSION = 1
SUPPORTED_ATTACK_VERSIONS = (1, 2)

_DAMAGE_TYPES: dict[str, DamageType] = {member.value: member for member in DamageType}
_KNOCKBACK_MODES = ("from_attacker", "fixed")
_SHAPE_KINDS = {member.value: member for member in ShapeKind}
_EASING_KINDS = {member.value: member for member in EasingKind}
_ANCHOR_KINDS = {member.value: member for member in AnchorKind}


def _defaults(cls: type) -> dict[str, Any]:
    """The dataclass's own defaults, keyed by field name.

    Read from ``dataclasses.fields`` rather than restated as literals beside
    each reader. A hand-copied default is a second place to forget when a field
    is added, and it fails silently: the loader would keep using a value the
    dataclass no longer has, and the two would disagree with nothing to say so.

    This is *values* only. Field names come from :func:`_field_names`, because
    a field with no default is still a key the reader accepts -- requiring it in
    JSON is enforced by ``_required``, and refusing it is enforced by
    ``_reject_unknown``.
    """
    return {field.name: field.default for field in fields(cls) if field.default is not MISSING}


def _field_names(cls: type) -> frozenset[str]:
    """Every field name of ``cls``, defaulted or not."""
    return frozenset(field.name for field in fields(cls))


_HIT_DEFAULTS = _defaults(HitProperties)
_HITBOX_DEFAULTS = _defaults(HitboxSpec)
_KEYFRAME_DEFAULTS = _defaults(HitboxKeyframe)
_PHASE_DEFAULTS = _defaults(PhaseDefinition)
_ATTACK_DEFAULTS = _defaults(AttackDefinition)
_KNOCKBACK_DEFAULTS = _defaults(KnockbackConfig)

#: Accepted spelling of ``anchor`` from before the field was renamed. Still
#: read, so a file written against the old name keeps working; still listed as
#: allowed, so the alias is a documented spelling rather than a typo that only
#: happens to work.
_LEGACY_ANCHOR_KEY = "follow"

#: The pre-``hitboxes`` per-phase hitbox spelling. Still read, so a file
#: authored against the v1 shape keeps loading; kept as a named set because
#: :func:`_read_phase` uses it twice -- once to accept those keys, once to
#: refuse them next to a ``hitboxes`` list -- and the second use has to name
#: every key that ``hitboxes`` subsumes, which the v1 list omitted.
_LEGACY_HITBOX_FIELDS = frozenset(
    {
        "hitbox_size",
        "hitbox_offset",
        "hitbox_keyframes",
        "extra_hitboxes",
        "hitbox_shape",
        "hitbox_angle",
        "hitbox_easing",
        "hitbox_anchor",
        "hitbox_anchor_offset",
    }
)


def _required(mapping: dict[str, Any], key: str, where: str) -> Any:
    """Fetch a mandatory JSON field with a precise location in the error."""
    if key not in mapping:
        raise GameplayDataError(f"{where}: missing required field {key!r}")
    return mapping[key]


def _reject_unknown(raw: dict[str, Any], allowed: frozenset[str], where: str) -> None:
    """Refuse any key the level below does not read.

    A typo in a hand-edited balance file must fail loudly. Silently defaulting
    it is the worst outcome available: the game boots, the attack exists, and
    the field that was meant to change it silently did not -- so a designer
    tuning a number sees no effect and concludes the number is wrong.
    """
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise GameplayDataError(
            f"{where}: unknown field(s) {', '.join(repr(key) for key in unknown)}; "
            f"expected one of {', '.join(sorted(allowed))}"
        )


def _pair_of_floats(value: Any, where: str) -> tuple[float, float]:
    """Parse a JSON ``[x, y]`` pair into a float tuple."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise GameplayDataError(f"{where}: expected a [x, y] pair, got {value!r}")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-numeric pair entry: {value!r}") from exc


def _read_knockback(raw: Any, where: str) -> KnockbackConfig:
    """Parse a knockback block (power pair + mode)."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: knockback must be an object, got {raw!r}")
    _reject_unknown(raw, _field_names(KnockbackConfig), where)
    power = _pair_of_floats(_required(raw, "power", where), f"{where}.power")
    mode = raw.get("mode", _KNOCKBACK_DEFAULTS["mode"])
    if mode not in _KNOCKBACK_MODES:
        raise GameplayDataError(f"{where}.mode: unknown mode {mode!r}")
    return KnockbackConfig(power=power, mode=mode)  # type: ignore[arg-type]


def _read_tags(raw: Any, where: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(tag, str) or not tag for tag in raw):
        raise GameplayDataError(f"{where}: 'tags' must be a list of non-empty strings")
    return tuple(raw)


def _read_hit(raw: Any, where: str) -> HitProperties:
    """Parse a hit block into :class:`HitProperties`."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: hit must be an object, got {raw!r}")
    _reject_unknown(raw, _field_names(HitProperties) | {"knockback"}, where)
    damage_type = _required(raw, "damage_type", where)
    if damage_type not in _DAMAGE_TYPES:
        raise GameplayDataError(f"{where}.damage_type: unknown type {damage_type!r}")
    try:
        return HitProperties(
            damage=float(_required(raw, "damage", where)),
            knockback=_read_knockback(raw.get("knockback", {}), f"{where}.knockback"),
            damage_type=_DAMAGE_TYPES[damage_type],
            stagger=float(raw.get("stagger", _HIT_DEFAULTS["stagger"])),
            super_armor_break=bool(raw.get("super_armor_break", _HIT_DEFAULTS["super_armor_break"])),
            is_finisher=bool(raw.get("is_finisher", _HIT_DEFAULTS["is_finisher"])),
            juggle_gravity_mult=float(
                raw.get("juggle_gravity_mult", _HIT_DEFAULTS["juggle_gravity_mult"])
            ),
            otg_allowed=bool(raw.get("otg_allowed", _HIT_DEFAULTS["otg_allowed"])),
            unblockable=bool(raw.get("unblockable", _HIT_DEFAULTS["unblockable"])),
            priority=int(raw.get("priority", _HIT_DEFAULTS["priority"])),
            clash=str(raw.get("clash", _HIT_DEFAULTS["clash"])),
            height=str(raw.get("height", _HIT_DEFAULTS["height"])),
            hit_level=str(raw.get("hit_level", _HIT_DEFAULTS["hit_level"])),
            block_mask=str(raw.get("block_mask", _HIT_DEFAULTS["block_mask"])),
            tags=_read_tags(raw.get("tags"), f"{where}.tags"),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid hit value: {exc}") from exc


def _enum_value(values: dict[str, Any], raw: Any, where: str, default: Any) -> Any:
    if raw is None:
        return default
    if raw not in values:
        raise GameplayDataError(f"{where}: unknown value {raw!r}")
    return values[raw]


def _read_hitbox_spec(raw: Any, where: str) -> HitboxSpec:
    """Parse one hitbox specification, including advanced shape fields."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: hitbox must be an object, got {raw!r}")
    _reject_unknown(raw, _field_names(HitboxSpec) | {_LEGACY_ANCHOR_KEY}, where)
    try:
        return HitboxSpec(
            size=_pair_of_floats(_required(raw, "size", where), f"{where}.size"),
            offset=_pair_of_floats(_required(raw, "offset", where), f"{where}.offset"),
            keyframes=_read_hitbox_keyframes(raw.get("keyframes"), f"{where}.keyframes"),
            shape=_enum_value(
                _SHAPE_KINDS,
                raw.get("shape"),
                f"{where}.shape",
                _HITBOX_DEFAULTS["shape"],
            ),
            angle=float(raw.get("angle", _HITBOX_DEFAULTS["angle"])),
            easing=_enum_value(
                _EASING_KINDS,
                raw.get("easing"),
                f"{where}.easing",
                _HITBOX_DEFAULTS["easing"],
            ),
            anchor=_enum_value(
                _ANCHOR_KINDS,
                raw.get("anchor", raw.get(_LEGACY_ANCHOR_KEY)),
                f"{where}.anchor",
                _HITBOX_DEFAULTS["anchor"],
            ),
            anchor_offset=_pair_of_floats(
                raw.get("anchor_offset", _HITBOX_DEFAULTS["anchor_offset"]),
                f"{where}.anchor_offset",
            ),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid hitbox: {exc}") from exc


def _read_extra_hitboxes(raw: Any, where: str) -> tuple[HitboxSpec, ...]:
    """Parse the optional ``extra_hitboxes`` list (empty when absent)."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise GameplayDataError(f"{where}: 'extra_hitboxes' must be a list")
    return tuple(_read_hitbox_spec(entry, f"{where}[{index}]") for index, entry in enumerate(raw))


def _read_hitbox_keyframe(raw: Any, where: str) -> HitboxKeyframe:
    """Parse one ``{"frame": N, "size": [...], "offset": [...]}`` sample."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: hitbox keyframe must be an object, got {raw!r}")
    _reject_unknown(raw, _field_names(HitboxKeyframe), where)
    try:
        return HitboxKeyframe(
            frame=int(_required(raw, "frame", where)),
            size=_pair_of_floats(_required(raw, "size", where), f"{where}.size"),
            offset=_pair_of_floats(_required(raw, "offset", where), f"{where}.offset"),
            angle=float(raw.get("angle", _KEYFRAME_DEFAULTS["angle"])),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid hitbox keyframe: {exc}") from exc


def _read_hitbox_keyframes(raw: Any, where: str) -> tuple[HitboxKeyframe, ...]:
    """Parse the optional ``hitbox_keyframes`` list (empty when absent)."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise GameplayDataError(f"{where}: 'hitbox_keyframes' must be a list")
    return tuple(
        _read_hitbox_keyframe(entry, f"{where}[{index}]") for index, entry in enumerate(raw)
    )


def _read_hitboxes(raw: Any, where: str) -> tuple[HitboxSpec, ...]:
    if not isinstance(raw, list) or not raw:
        raise GameplayDataError(f"{where}: 'hitboxes' must be a non-empty list")
    return tuple(_read_hitbox_spec(entry, f"{where}[{index}]") for index, entry in enumerate(raw))


def _read_phase(raw: Any, where: str) -> PhaseDefinition:
    """Parse one phase block into :class:`PhaseDefinition`."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: phase must be an object, got {raw!r}")
    hitboxes = raw.get("hitboxes")
    # The v2 ``hitboxes`` list already carries shape, angle, easing and anchor
    # per box, so mixing any of them alongside it is ambiguous rather than
    # merely redundant -- and the original guard-fou listed only the geometry
    # keys, silently dropping those four beside a ``hitboxes`` list.
    legacy_fields = frozenset(_LEGACY_HITBOX_FIELDS)
    _reject_unknown(raw, _field_names(PhaseDefinition) | {"hitboxes"} | legacy_fields, where)
    if hitboxes is not None and legacy_fields.intersection(raw):
        raise GameplayDataError(
            f"{where}: 'hitboxes' cannot be combined with legacy hitbox fields "
            f"({', '.join(sorted(legacy_fields.intersection(raw)))})"
        )
    try:
        extras: tuple[HitboxSpec, ...]
        if hitboxes is None:
            primary = HitboxSpec(
                size=_pair_of_floats(_required(raw, "hitbox_size", where), f"{where}.hitbox_size"),
                offset=_pair_of_floats(
                    _required(raw, "hitbox_offset", where), f"{where}.hitbox_offset"
                ),
                keyframes=_read_hitbox_keyframes(
                    raw.get("hitbox_keyframes"), f"{where}.hitbox_keyframes"
                ),
                shape=_enum_value(
                    _SHAPE_KINDS,
                    raw.get("hitbox_shape"),
                    f"{where}.hitbox_shape",
                    _PHASE_DEFAULTS["hitbox_shape"],
                ),
                angle=float(raw.get("hitbox_angle", _PHASE_DEFAULTS["hitbox_angle"])),
                easing=_enum_value(
                    _EASING_KINDS,
                    raw.get("hitbox_easing"),
                    f"{where}.hitbox_easing",
                    _PHASE_DEFAULTS["hitbox_easing"],
                ),
                anchor=_enum_value(
                    _ANCHOR_KINDS,
                    raw.get("hitbox_anchor"),
                    f"{where}.hitbox_anchor",
                    _PHASE_DEFAULTS["hitbox_anchor"],
                ),
                anchor_offset=_pair_of_floats(
                    raw.get("hitbox_anchor_offset", _PHASE_DEFAULTS["hitbox_anchor_offset"]),
                    f"{where}.hitbox_anchor_offset",
                ),
            )
            extras = _read_extra_hitboxes(raw.get("extra_hitboxes"), f"{where}.extra_hitboxes")
        else:
            specs = _read_hitboxes(hitboxes, f"{where}.hitboxes")
            primary, *extra_specs = specs
            extras = tuple(extra_specs)
        return PhaseDefinition(
            startup_frames=int(_required(raw, "startup_frames", where)),
            active_frames=int(_required(raw, "active_frames", where)),
            recovery_frames=int(_required(raw, "recovery_frames", where)),
            hitbox_size=primary.size,
            hitbox_offset=primary.offset,
            hit=_read_hit(_required(raw, "hit", where), f"{where}.hit"),
            hitbox_shape=primary.shape,
            hitbox_angle=primary.angle,
            hitbox_easing=primary.easing,
            hitbox_anchor=primary.anchor,
            hitbox_anchor_offset=primary.anchor_offset,
            extra_hitboxes=extras,
            hitbox_keyframes=primary.keyframes,
            reset_targets=bool(raw.get("reset_targets", _PHASE_DEFAULTS["reset_targets"])),
            cancel_into=tuple(raw.get("cancel_into", _PHASE_DEFAULTS["cancel_into"])),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid phase value: {exc}") from exc


def read_attack_definition(raw: Any, where: str) -> AttackDefinition:
    """Parse one attack block into :class:`AttackDefinition`."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: attack must be an object, got {raw!r}")
    _reject_unknown(raw, _field_names(AttackDefinition), where)
    raw_phases = _required(raw, "phases", where)
    if not isinstance(raw_phases, list) or not raw_phases:
        raise GameplayDataError(f"{where}: 'phases' must be a non-empty list")
    try:
        return AttackDefinition(
            phases=tuple(
                _read_phase(phase, f"{where}.phases[{index}]")
                for index, phase in enumerate(raw_phases)
            ),
            cooldown=float(_required(raw, "cooldown", where)),
            lock_direction=bool(raw.get("lock_direction", _ATTACK_DEFAULTS["lock_direction"])),
            combo_reset=bool(raw.get("combo_reset", _ATTACK_DEFAULTS["combo_reset"])),
            chargeable=bool(raw.get("chargeable", _ATTACK_DEFAULTS["chargeable"])),
            max_charge_time=float(
                raw.get("max_charge_time", _ATTACK_DEFAULTS["max_charge_time"])
            ),
            charge_move_multiplier=float(
                raw.get("charge_move_multiplier", _ATTACK_DEFAULTS["charge_move_multiplier"])
            ),
            uninterruptible=bool(
                raw.get("uninterruptible", _ATTACK_DEFAULTS["uninterruptible"])
            ),
            lunge_speed_multiplier=float(
                raw.get("lunge_speed_multiplier", _ATTACK_DEFAULTS["lunge_speed_multiplier"])
            ),
            attack_move_multiplier=float(
                raw.get("attack_move_multiplier", _ATTACK_DEFAULTS["attack_move_multiplier"])
            ),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid attack value: {exc}") from exc


def read_attacks_file(path: str | Path) -> dict[str, dict[str, AttackDefinition]]:
    """Load every named attack set from an ``attacks.json`` file."""
    raw = read_json_object(path, SUPPORTED_ATTACK_VERSIONS)
    raw_sets = _required(raw, "sets", str(path))
    if not isinstance(raw_sets, dict):
        raise GameplayDataError(f"{path}: 'sets' must be an object")
    sets: dict[str, dict[str, AttackDefinition]] = {}
    for set_name, raw_attacks in raw_sets.items():
        if not isinstance(raw_attacks, dict):
            raise GameplayDataError(f"{path}#{set_name}: attack set must be an object")
        # Comment keys, at either level: JSON has no comments, so an
        # underscore prefix is the conventional way to park one in a data file.
        # They are inert, so they are dropped rather than read as an attack --
        # refusing them would push designers to strip their own annotations
        # before committing, and a data file nobody dares annotate is one
        # nobody tunes.
        if set_name.startswith("_"):
            continue
        raw_attacks = {name: value for name, value in raw_attacks.items() if not name.startswith("_")}
        if not raw_attacks:
            raise GameplayDataError(f"{path}#{set_name}: attack set must name at least one attack")
        sets[set_name] = {
            name: read_attack_definition(definition, f"{path}#{set_name}.{name}")
            for name, definition in raw_attacks.items()
        }
    return sets


def _keyframe_to_dict(keyframe: HitboxKeyframe) -> dict[str, Any]:
    result: dict[str, Any] = {
        "frame": keyframe.frame,
        "size": list(keyframe.size),
        "offset": list(keyframe.offset),
    }
    if keyframe.angle != 0.0:
        result["angle"] = keyframe.angle
    return result


def _hitbox_spec_to_dict(spec: HitboxSpec) -> dict[str, Any]:
    result: dict[str, Any] = {
        "size": list(spec.size),
        "offset": list(spec.offset),
        "keyframes": [_keyframe_to_dict(keyframe) for keyframe in spec.keyframes],
    }
    if spec.shape is not ShapeKind.AABB:
        result["shape"] = spec.shape.value
    if spec.angle != 0.0:
        result["angle"] = spec.angle
    if spec.easing is not EasingKind.LINEAR:
        result["easing"] = spec.easing.value
    if spec.anchor is not AnchorKind.CENTER:
        result["anchor"] = spec.anchor.value
    if spec.anchor_offset != (0.0, 0.0):
        result["anchor_offset"] = list(spec.anchor_offset)
    return result


def attack_definition_to_dict(definition: AttackDefinition) -> dict[str, Any]:
    """Serialize an :class:`AttackDefinition` back to its JSON shape."""
    return {
        "phases": [
            {
                "startup_frames": phase.startup_frames,
                "active_frames": phase.active_frames,
                "recovery_frames": phase.recovery_frames,
                "hitbox_size": list(phase.hitbox_size),
                "hitbox_offset": list(phase.hitbox_offset),
                **(
                    {
                        "hitbox_shape": phase.hitbox_shape.value,
                        "hitbox_angle": phase.hitbox_angle,
                        "hitbox_easing": phase.hitbox_easing.value,
                        "hitbox_anchor": phase.hitbox_anchor.value,
                        "hitbox_anchor_offset": list(phase.hitbox_anchor_offset),
                    }
                    if phase.hitbox_shape is not ShapeKind.AABB
                    else {}
                ),
                **(
                    {"hitbox_anchor": phase.hitbox_anchor.value}
                    if phase.hitbox_shape is ShapeKind.AABB
                    and phase.hitbox_anchor is not AnchorKind.CENTER
                    else {}
                ),
                **(
                    {"hitbox_anchor_offset": list(phase.hitbox_anchor_offset)}
                    if phase.hitbox_anchor_offset != (0.0, 0.0)
                    else {}
                ),
                "hit": {
                    "damage": phase.hit.damage,
                    "knockback": {
                        "power": list(phase.hit.knockback.power),
                        "mode": phase.hit.knockback.mode,
                    },
                    "damage_type": phase.hit.damage_type.value,
                    "stagger": phase.hit.stagger,
                    "super_armor_break": phase.hit.super_armor_break,
                    "is_finisher": phase.hit.is_finisher,
                    "juggle_gravity_mult": phase.hit.juggle_gravity_mult,
                    "otg_allowed": phase.hit.otg_allowed,
                    "unblockable": phase.hit.unblockable,
                    "priority": phase.hit.priority,
                    "clash": phase.hit.clash,
                    "height": phase.hit.height,
                    "hit_level": phase.hit.hit_level,
                    "block_mask": phase.hit.block_mask,
                    "tags": list(phase.hit.tags),
                },
                "extra_hitboxes": [_hitbox_spec_to_dict(spec) for spec in phase.extra_hitboxes],
                "hitbox_keyframes": [
                    _keyframe_to_dict(keyframe) for keyframe in phase.hitbox_keyframes
                ],
                "reset_targets": phase.reset_targets,
                "cancel_into": list(phase.cancel_into),
            }
            for phase in definition.phases
        ],
        "cooldown": definition.cooldown,
        "lock_direction": definition.lock_direction,
        "combo_reset": definition.combo_reset,
        "chargeable": definition.chargeable,
        "max_charge_time": definition.max_charge_time,
        "charge_move_multiplier": definition.charge_move_multiplier,
        "uninterruptible": definition.uninterruptible,
        "lunge_speed_multiplier": definition.lunge_speed_multiplier,
        "attack_move_multiplier": definition.attack_move_multiplier,
    }


def attack_definition_to_v2_dict(definition: AttackDefinition) -> dict[str, Any]:
    """Serialize an attack with the canonical ``hitboxes`` list."""
    raw = attack_definition_to_dict(definition)
    for phase, phase_data in zip(definition.phases, raw["phases"], strict=True):
        hitboxes = [_hitbox_spec_to_dict(phase.hitbox_spec)]
        hitboxes.extend(_hitbox_spec_to_dict(spec) for spec in phase.extra_hitboxes)
        for key in (
            "hitbox_size",
            "hitbox_offset",
            "hitbox_shape",
            "hitbox_angle",
            "hitbox_easing",
            "hitbox_anchor",
            "hitbox_anchor_offset",
            "hitbox_keyframes",
            "extra_hitboxes",
        ):
            phase_data.pop(key, None)
        phase_data["hitboxes"] = hitboxes
    return raw


def attacks_document(
    attack_sets: Mapping[str, Mapping[str, AttackDefinition]],
    version: int = ATTACKS_VERSION,
) -> dict[str, Any]:
    """Serialize a complete attack bundle into the loadable JSON document shape."""
    serializer = attack_definition_to_dict if version == 1 else attack_definition_to_v2_dict
    return {
        "version": version,
        "sets": {
            set_name: {name: serializer(definition) for name, definition in attacks.items()}
            for set_name, attacks in attack_sets.items()
        },
    }


def write_attacks_file(
    path: str | Path,
    attack_sets: Mapping[str, Mapping[str, AttackDefinition]],
    version: int = ATTACKS_VERSION,
) -> Path:
    """Write a complete attack bundle atomically and return its destination."""
    import json

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(
            attacks_document(attack_sets, version),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination
