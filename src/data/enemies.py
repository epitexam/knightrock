"""Typed JSON loader for enemy configs (Phase 3 #4).

``enemies.json`` maps enemy type names to :class:`EnemyConfig` values::

    {"version": 1, "enemies": {"goblin": {"size": [36, 48], ...}}}

Each entry references its moves via ``attacks``: either the name of an
attack set already loaded from ``attacks.json`` ("goblin") or a private
inline attack table (the pattern ``dummy`` uses).  Animations are plain
``{state: sprite_sheet_directory}`` maps, mirroring the
``EnemyConfig.animations`` field added in Phase 2 #1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.combat.frame_data import AttackDefinition
from src.data.attacks import read_attack_definition
from src.data.errors import GameplayDataError, read_json_object
from src.entities.enemies.schema import EnemyConfig
from src.entities.hurtbox_zones import hurtbox_zones_to_dict, read_hurtbox_zones

ENEMIES_FILENAME = "enemies.json"
ENEMIES_VERSION = 1


def _required(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise GameplayDataError(f"{where}: missing required field {key!r}")
    return mapping[key]


def _pair_of_floats(value: Any, where: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise GameplayDataError(f"{where}: expected a [x, y] pair, got {value!r}")
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-numeric pair entry: {value!r}") from exc


def _triple_of_ints(value: Any, where: str) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        raise GameplayDataError(f"{where}: expected a [r, g, b] triple, got {value!r}")
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: non-integer color entry: {value!r}") from exc


def _read_animations(raw: Any, where: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: animations must be an object")
    for state, directory in raw.items():
        if not isinstance(directory, str):
            raise GameplayDataError(f"{where}.{state}: directory must be a string")
    return dict(raw)


def read_enemy_config(
    raw: Any,
    where: str,
    attack_sets: dict[str, dict[str, AttackDefinition]],
) -> EnemyConfig:
    """Parse one enemy block into :class:`EnemyConfig`."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: enemy must be an object, got {raw!r}")
    raw_attacks = _required(raw, "attacks", where)
    attacks: dict[str, AttackDefinition]
    if isinstance(raw_attacks, str):
        if raw_attacks not in attack_sets:
            raise GameplayDataError(f"{where}: unknown attack set {raw_attacks!r}")
        attacks = dict(attack_sets[raw_attacks])
    elif isinstance(raw_attacks, dict):
        attacks = {
            name: read_attack_definition(definition, f"{where}.attacks.{name}")
            for name, definition in raw_attacks.items()
        }
    else:
        raise GameplayDataError(f"{where}: 'attacks' must be a set name or an object")
    try:
        return EnemyConfig(
            size=_pair_of_floats(_required(raw, "size", where), f"{where}.size"),
            color=_triple_of_ints(_required(raw, "color", where), f"{where}.color"),
            health=float(_required(raw, "health", where)),
            attacks=attacks,
            attack_name=raw.get("attack_name"),
            max_health=(float(raw["max_health"]) if raw.get("max_health") is not None else None),
            hitbox_inflate=_pair_of_floats(
                raw.get("hitbox_inflate", [0.0, 0.0]), f"{where}.hitbox_inflate"
            ),
            hurtbox_inflate=_pair_of_floats(
                raw.get("hurtbox_inflate", [0.0, 0.0]), f"{where}.hurtbox_inflate"
            ),
            # P2: absent field keeps the legacy fallback on ``hurtbox_inflate``.
            hurtbox_zones=read_hurtbox_zones(raw.get("hurtbox_zones"), f"{where}.hurtbox_zones"),
            chase_speed=float(raw.get("chase_speed", 120.0)),
            vision_range=float(raw.get("vision_range", 300.0)),
            attack_range=float(raw.get("attack_range", 60.0)),
            patrol_interval=float(raw.get("patrol_interval", 2.0)),
            idle_duration=float(raw.get("idle_duration", 0.5)),
            has_ai=bool(raw.get("has_ai", True)),
            pushable=bool(raw.get("pushable", True)),
            super_armor=bool(raw.get("super_armor", False)),
            passive_friction=float(raw.get("passive_friction", 10.0)),
            can_jump=bool(raw.get("can_jump", False)),
            jump_height=float(raw.get("jump_height", 500.0)),
            jump_cooldown=float(raw.get("jump_cooldown", 1.0)),
            leap_speed_mult=float(raw.get("leap_speed_mult", 1.0)),
            parry_stun_threshold=(
                int(raw["parry_stun_threshold"])
                if raw.get("parry_stun_threshold") is not None
                else None
            ),
            parry_stun_duration=float(raw.get("parry_stun_duration", 0.0)),
            animations=_read_animations(raw.get("animations"), f"{where}.animations"),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid enemy value: {exc}") from exc


def read_enemies_file(
    path: str | Path,
    attack_sets: dict[str, dict[str, AttackDefinition]],
) -> dict[str, EnemyConfig]:
    """Load every enemy type from an ``enemies.json`` file."""
    raw = read_json_object(path, ENEMIES_VERSION)
    raw_enemies = _required(raw, "enemies", str(path))
    if not isinstance(raw_enemies, dict):
        raise GameplayDataError(f"{path}: 'enemies' must be an object")
    return {
        name: read_enemy_config(definition, f"{path}#{name}", attack_sets)
        for name, definition in raw_enemies.items()
    }


def enemy_config_to_dict(config: EnemyConfig) -> dict[str, Any]:
    """Serialize an :class:`EnemyConfig` back to its JSON shape.

    Attacks are serialized inline (never as a set name) so the file is
    self-contained for designer edits; set references stay a load-time
    convenience.  ``attack_set`` is recovered on demand by comparing
    identity with the known sets.
    """
    from src.data.attacks import attack_definition_to_dict

    return {
        "size": list(config.size),
        "color": list(config.color),
        "health": config.health,
        "attacks": {
            name: attack_definition_to_dict(attack) for name, attack in config.attacks.items()
        },
        "attack_name": config.attack_name,
        "max_health": config.max_health,
        "hitbox_inflate": list(config.hitbox_inflate),
        "hurtbox_inflate": list(config.hurtbox_inflate),
        # P2 multi-hurtbox: key omitted for legacy configs (JSON shape kept).
        **(
            {"hurtbox_zones": hurtbox_zones_to_dict(config.hurtbox_zones)}
            if config.hurtbox_zones is not None
            else {}
        ),
        "chase_speed": config.chase_speed,
        "vision_range": config.vision_range,
        "attack_range": config.attack_range,
        "patrol_interval": config.patrol_interval,
        "idle_duration": config.idle_duration,
        "has_ai": config.has_ai,
        "pushable": config.pushable,
        "super_armor": config.super_armor,
        "passive_friction": config.passive_friction,
        "can_jump": config.can_jump,
        "jump_height": config.jump_height,
        "jump_cooldown": config.jump_cooldown,
        "leap_speed_mult": config.leap_speed_mult,
        "parry_stun_threshold": config.parry_stun_threshold,
        "parry_stun_duration": config.parry_stun_duration,
        "animations": dict(config.animations),
    }
