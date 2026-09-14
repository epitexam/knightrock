"""Typed JSON loader for the player config (Phase 3 #4).

``player.json`` holds the *overrides* that distinguish
``DEFAULT_PLAYER_CONFIG`` from the bare ``PlayerConfig()`` defaults
(pink sprite, ``max_wall_jumps: "inf"``, ``"player"`` attack set)::

    {"version": 1, "player": {"color": [255, 120, 200], ...}}

Only the fields that differ from ``PlayerConfig()`` are required in the
file; everything else falls back to the dataclass defaults.  ``"inf"`` is
spelled as a string because JSON has no infinity literal.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from src.combat.frame_data import AttackDefinition
from src.data.errors import GameplayDataError, read_json_object
from src.entities.player_config import PlayerConfig

PLAYER_FILENAME = "player.json"
PLAYER_VERSION = 1


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


def _read_wall_jumps(value: Any, where: str) -> int | float:
    """Parse ``max_wall_jumps``: an int, ``"inf"``, or a float."""
    if isinstance(value, str):
        if value == "inf":
            return math.inf
        raise GameplayDataError(f"{where}: unknown wall-jump value {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid wall-jump value: {value!r}") from exc
    return int(number) if number.is_integer() and number >= 0 else number


def read_player_config(
    raw: Any,
    where: str,
    attack_sets: dict[str, dict[str, AttackDefinition]],
) -> PlayerConfig:
    """Merge a ``player`` JSON block over ``PlayerConfig()`` defaults."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: player must be an object, got {raw!r}")
    base = PlayerConfig()
    raw_attacks = raw.get("attack_set")
    attacks: dict[str, AttackDefinition] | None = None
    if raw_attacks is not None:
        if not isinstance(raw_attacks, str) or raw_attacks not in attack_sets:
            raise GameplayDataError(f"{where}: unknown attack set {raw_attacks!r}")
        attacks = dict(attack_sets[raw_attacks])
    try:
        return PlayerConfig(
            size=_pair_of_floats(raw.get("size", list(base.size)), f"{where}.size"),
            color=_triple_of_ints(raw.get("color", list(base.color)), f"{where}.color"),
            health=float(raw.get("health", base.health)),
            max_health=float(raw.get("max_health", base.max_health)),
            hitbox_inflate=_pair_of_floats(
                raw.get("hitbox_inflate", list(base.hitbox_inflate)), f"{where}.hitbox_inflate"
            ),
            hurtbox_inflate=_pair_of_floats(
                raw.get("hurtbox_inflate", list(base.hurtbox_inflate)), f"{where}.hurtbox_inflate"
            ),
            attacks=attacks if attacks is not None else dict(base.attacks),
            speed=float(raw.get("speed", base.speed)),
            floor_control=float(raw.get("floor_control", base.floor_control)),
            air_control=float(raw.get("air_control", base.air_control)),
            jump_height=float(raw.get("jump_height", base.jump_height)),
            wall_jump_height=float(raw.get("wall_jump_height", base.wall_jump_height)),
            wall_jump_push_multiplier=float(
                raw.get("wall_jump_push_multiplier", base.wall_jump_push_multiplier)
            ),
            wall_jump_lock_duration=float(
                raw.get("wall_jump_lock_duration", base.wall_jump_lock_duration)
            ),
            wall_jump_min_lock=float(raw.get("wall_jump_min_lock", base.wall_jump_min_lock)),
            wall_slide_speed=float(raw.get("wall_slide_speed", base.wall_slide_speed)),
            max_midair_jumps=int(raw.get("max_midair_jumps", base.max_midair_jumps)),
            max_wall_jumps=(
                _read_wall_jumps(raw["max_wall_jumps"], f"{where}.max_wall_jumps")
                if "max_wall_jumps" in raw
                else base.max_wall_jumps
            ),
            coyote_duration=float(raw.get("coyote_duration", base.coyote_duration)),
            jump_buffer_duration=float(raw.get("jump_buffer_duration", base.jump_buffer_duration)),
            max_block_stamina=float(raw.get("max_block_stamina", base.max_block_stamina)),
            block_cooldown_normal=float(
                raw.get("block_cooldown_normal", base.block_cooldown_normal)
            ),
            block_cooldown_broken=float(
                raw.get("block_cooldown_broken", base.block_cooldown_broken)
            ),
            max_dash_charges=int(raw.get("max_dash_charges", base.max_dash_charges)),
            dash_speed=float(raw.get("dash_speed", base.dash_speed)),
            dash_duration=float(raw.get("dash_duration", base.dash_duration)),
            dash_friction=float(raw.get("dash_friction", base.dash_friction)),
            dash_penalty_duration=float(
                raw.get("dash_penalty_duration", base.dash_penalty_duration)
            ),
            dash_recharge_time=float(raw.get("dash_recharge_time", base.dash_recharge_time)),
            dash_gravity_mult=float(raw.get("dash_gravity_mult", base.dash_gravity_mult)),
            hurt_duration=float(raw.get("hurt_duration", base.hurt_duration)),
            invincibility_duration=float(
                raw.get("invincibility_duration", base.invincibility_duration)
            ),
            faction=str(raw.get("faction", base.faction)),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid player value: {exc}") from exc


def read_player_file(
    path: str | Path, attack_sets: dict[str, dict[str, AttackDefinition]]
) -> PlayerConfig:
    """Load the player config block from a ``player.json`` file."""
    raw = read_json_object(path, PLAYER_VERSION)
    return read_player_config(raw.get("player", {}), str(path), attack_sets)


def player_config_to_dict(config: PlayerConfig, attack_set: str | None) -> dict[str, Any]:
    """Serialize the diff between ``config`` and ``PlayerConfig()``."""
    base = PlayerConfig()
    diff: dict[str, Any] = {}
    if attack_set is not None:
        diff["attack_set"] = attack_set
    for key in (
        "speed",
        "floor_control",
        "air_control",
        "jump_height",
        "wall_jump_height",
        "wall_jump_push_multiplier",
        "wall_jump_lock_duration",
        "wall_jump_min_lock",
        "wall_slide_speed",
        "max_midair_jumps",
        "coyote_duration",
        "jump_buffer_duration",
        "max_block_stamina",
        "block_cooldown_normal",
        "block_cooldown_broken",
        "max_dash_charges",
        "dash_speed",
        "dash_duration",
        "dash_friction",
        "dash_penalty_duration",
        "dash_recharge_time",
        "dash_gravity_mult",
        "hurt_duration",
        "invincibility_duration",
        "health",
        "max_health",
        "faction",
    ):
        value = getattr(config, key)
        if getattr(base, key) != value:
            diff[key] = value
    for key in ("size", "hitbox_inflate", "hurtbox_inflate"):
        value = list(getattr(config, key))
        if list(getattr(base, key)) != value:
            diff[key] = value
    if list(base.color) != list(config.color):
        diff["color"] = list(config.color)
    if isinstance(config.max_wall_jumps, float) and config.max_wall_jumps == math.inf:
        diff["max_wall_jumps"] = "inf"
    elif base.max_wall_jumps != config.max_wall_jumps:
        diff["max_wall_jumps"] = config.max_wall_jumps
    return diff
