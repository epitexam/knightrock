"""Typed JSON loader for attack frame data (Phase 3 #4).

``attacks.json`` groups attacks in named sets so each consumer only sees
its own moves::

    {"version": 1, "sets": {"player": {"light_attack": {...}, ...}, ...}}

Every structural field of ``AttackDefinition`` / ``PhaseDefinition`` /
``HitProperties`` is required in JSON except trailing documented tuning
defaults (``mode``, ``stagger``, flags, multipliers...).  Unknown keys
always raise: a typo must fail loudly, never silently use a default.
"""

from __future__ import annotations

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
from src.data.errors import GameplayDataError, read_json_object

ATTACKS_FILENAME = "attacks.json"
ATTACKS_VERSION = 1

_DAMAGE_TYPES: dict[str, DamageType] = {member.value: member for member in DamageType}
_KNOCKBACK_MODES = ("from_attacker", "fixed")


def _required(mapping: dict[str, Any], key: str, where: str) -> Any:
    """Fetch a mandatory JSON field with a precise location in the error."""
    if key not in mapping:
        raise GameplayDataError(f"{where}: missing required field {key!r}")
    return mapping[key]


def _pair_of_floats(value: Any, where: str) -> tuple[float, float]:
    """Parse a JSON ``[x, y]`` pair into a float tuple."""
    if not isinstance(value, list) or len(value) != 2:
        raise GameplayDataError(f"{where}: expected a [x, y] pair, got {value!r}")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-numeric pair entry: {value!r}") from exc


def _read_knockback(raw: Any, where: str) -> KnockbackConfig:
    """Parse a knockback block (power pair + mode)."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: knockback must be an object, got {raw!r}")
    power = _pair_of_floats(_required(raw, "power", where), f"{where}.power")
    mode = raw.get("mode", "from_attacker")
    if mode not in _KNOCKBACK_MODES:
        raise GameplayDataError(f"{where}.mode: unknown mode {mode!r}")
    return KnockbackConfig(power=power, mode=mode)  # type: ignore[arg-type]


def _read_hit(raw: Any, where: str) -> HitProperties:
    """Parse a hit block into :class:`HitProperties`."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: hit must be an object, got {raw!r}")
    damage_type = _required(raw, "damage_type", where)
    if damage_type not in _DAMAGE_TYPES:
        raise GameplayDataError(f"{where}.damage_type: unknown type {damage_type!r}")
    try:
        return HitProperties(
            damage=float(_required(raw, "damage", where)),
            knockback=_read_knockback(raw.get("knockback", {}), f"{where}.knockback"),
            damage_type=_DAMAGE_TYPES[damage_type],
            stagger=float(raw.get("stagger", 0.0)),
            super_armor_break=bool(raw.get("super_armor_break", False)),
            is_finisher=bool(raw.get("is_finisher", False)),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid hit value: {exc}") from exc


def _read_hitbox_spec(raw: Any, where: str) -> HitboxSpec:
    """Parse one ``{"size": [...], "offset": [...]}`` extra box."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: extra hitbox must be an object, got {raw!r}")
    try:
        return HitboxSpec(
            size=_pair_of_floats(_required(raw, "size", where), f"{where}.size"),
            offset=_pair_of_floats(_required(raw, "offset", where), f"{where}.offset"),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid extra hitbox: {exc}") from exc


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
    try:
        return HitboxKeyframe(
            frame=int(_required(raw, "frame", where)),
            size=_pair_of_floats(_required(raw, "size", where), f"{where}.size"),
            offset=_pair_of_floats(_required(raw, "offset", where), f"{where}.offset"),
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


def _read_phase(raw: Any, where: str) -> PhaseDefinition:
    """Parse one phase block into :class:`PhaseDefinition`."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: phase must be an object, got {raw!r}")
    try:
        return PhaseDefinition(
            startup_frames=int(_required(raw, "startup_frames", where)),
            active_frames=int(_required(raw, "active_frames", where)),
            recovery_frames=int(_required(raw, "recovery_frames", where)),
            hitbox_size=_pair_of_floats(
                _required(raw, "hitbox_size", where), f"{where}.hitbox_size"
            ),
            hitbox_offset=_pair_of_floats(
                _required(raw, "hitbox_offset", where), f"{where}.hitbox_offset"
            ),
            hit=_read_hit(_required(raw, "hit", where), f"{where}.hit"),
            extra_hitboxes=_read_extra_hitboxes(
                raw.get("extra_hitboxes"), f"{where}.extra_hitboxes"
            ),
            hitbox_keyframes=_read_hitbox_keyframes(
                raw.get("hitbox_keyframes"), f"{where}.hitbox_keyframes"
            ),
            reset_targets=bool(raw.get("reset_targets", True)),
            cancel_into=tuple(raw.get("cancel_into", ())),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid phase value: {exc}") from exc


def read_attack_definition(raw: Any, where: str) -> AttackDefinition:
    """Parse one attack block into :class:`AttackDefinition`."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: attack must be an object, got {raw!r}")
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
            lock_direction=bool(raw.get("lock_direction", False)),
            combo_reset=bool(raw.get("combo_reset", False)),
            chargeable=bool(raw.get("chargeable", False)),
            max_charge_time=float(raw.get("max_charge_time", 1.0)),
            charge_move_multiplier=float(raw.get("charge_move_multiplier", 1.0)),
            uninterruptible=bool(raw.get("uninterruptible", False)),
            lunge_speed_multiplier=float(raw.get("lunge_speed_multiplier", 0.35)),
            attack_move_multiplier=float(raw.get("attack_move_multiplier", 0.3)),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid attack value: {exc}") from exc


def read_attacks_file(path: str | Path) -> dict[str, dict[str, AttackDefinition]]:
    """Load every named attack set from an ``attacks.json`` file."""
    raw = read_json_object(path, ATTACKS_VERSION)
    raw_sets = _required(raw, "sets", str(path))
    if not isinstance(raw_sets, dict):
        raise GameplayDataError(f"{path}: 'sets' must be an object")
    sets: dict[str, dict[str, AttackDefinition]] = {}
    for set_name, raw_attacks in raw_sets.items():
        if not isinstance(raw_attacks, dict):
            raise GameplayDataError(f"{path}#{set_name}: attack set must be an object")
        sets[set_name] = {
            name: read_attack_definition(definition, f"{path}#{set_name}.{name}")
            for name, definition in raw_attacks.items()
        }
    return sets


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
                },
                "extra_hitboxes": [
                    {"size": list(spec.size), "offset": list(spec.offset)}
                    for spec in phase.extra_hitboxes
                ],
                "hitbox_keyframes": [
                    {
                        "frame": keyframe.frame,
                        "size": list(keyframe.size),
                        "offset": list(keyframe.offset),
                    }
                    for keyframe in phase.hitbox_keyframes
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
