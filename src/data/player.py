"""Typed JSON loader for the player config.

``player.json`` holds the *overrides* on the bare ``PlayerConfig()`` defaults
(pink sprite, ``max_wall_jumps: "inf"``, ``"player"`` attack set), and the
result is the player's whole configuration -- there is no copy in code::

    {"version": 1, "player": {"color": [255, 120, 200], ...}}

Only the fields that differ from ``PlayerConfig()`` are required in the
file; everything else falls back to the dataclass defaults.  ``"inf"`` is
spelled as a string because JSON has no infinity literal.
"""

from __future__ import annotations

import math
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

from src.combat.frame_data import AttackDefinition, MoveId
from src.data.errors import (
    GameplayDataError,
    pair_of_floats,
    read_int,
    read_json_object,
    read_number,
    reject_unknown,
    triple_of_ints,
)
from src.entities.hurtbox_zones import read_hurtbox_zones
from src.entities.player_config import PlayerConfig, _default_attacks

PLAYER_FILENAME = "player.json"
PLAYER_VERSION = 1


def _player_override_keys() -> frozenset[str]:
    """Every key ``player.json``'s block may carry.

    Derived from :class:`PlayerConfig`'s fields rather than written out: the
    block is an override layer, so it spells ``attack_set`` where the dataclass
    has ``attacks`` and skips nothing else. Listed by hand it would drift the
    moment a tuning field was added to ``PlayerConfig``, and the drift would be
    invisible -- an unknown key used to be ignored, so the new field would
    simply never be overridable, with nothing to say so.
    """
    return frozenset(field.name for field in fields(PlayerConfig)) - {"attacks"} | {"attack_set"}


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


def _value_defaults(cls: type) -> dict[str, Any]:
    """The dataclass's literal defaults, without invoking any default_factory."""
    return {field.name: field.default for field in fields(cls) if field.default is not MISSING}


_PLAYER_DEFAULTS = _value_defaults(PlayerConfig)


def read_player_config(
    raw: Any,
    where: str,
    attack_sets: dict[str, dict[MoveId, AttackDefinition]],
) -> PlayerConfig:
    """Merge a ``player`` JSON block over ``PlayerConfig()`` defaults."""
    if not isinstance(raw, dict):
        raise GameplayDataError(f"{where}: player must be an object, got {raw!r}")
    # Not the dataclass's field names: this block is an *override* layer over
    # ``PlayerConfig()``, so it spells a few of them differently and omits the
    # derived ones (the attack table is reached through ``attack_set``). The
    # allowed set is therefore the reader's own, listed once.
    reject_unknown(raw, _player_override_keys(), where)
    # The attack default is a factory that reads attacks.json; calling it here
    # would parse the whole table a second time for a value the `attack_set`
    # override below always replaces. Build the defaults from the fields'
    # *values*, skipping factories, and supply the already-loaded table.
    raw_attacks = raw.get("attack_set")
    attacks: dict[MoveId, AttackDefinition] | None = None
    if raw_attacks is not None:
        if not isinstance(raw_attacks, str) or raw_attacks not in attack_sets:
            raise GameplayDataError(f"{where}: unknown attack set {raw_attacks!r}")
        attacks = dict(attack_sets[MoveId(raw_attacks)])
    try:
        return PlayerConfig(
            size=pair_of_floats(raw.get("size", list(_PLAYER_DEFAULTS["size"])), f"{where}.size"),
            color=triple_of_ints(
                raw.get("color", list(_PLAYER_DEFAULTS["color"])), f"{where}.color"
            ),
            health=read_number(raw.get("health", _PLAYER_DEFAULTS["health"]), f"{where}.health"),
            max_health=read_number(
                raw.get("max_health", _PLAYER_DEFAULTS["max_health"]), f"{where}.max_health"
            ),
            hitbox_inflate=pair_of_floats(
                raw.get("hitbox_inflate", list(_PLAYER_DEFAULTS["hitbox_inflate"])),
                f"{where}.hitbox_inflate",
            ),
            hurtbox_inflate=pair_of_floats(
                raw.get("hurtbox_inflate", list(_PLAYER_DEFAULTS["hurtbox_inflate"])),
                f"{where}.hurtbox_inflate",
            ),
            # P2: absent field keeps the legacy fallback on ``hurtbox_inflate``.
            hurtbox_zones=read_hurtbox_zones(raw.get("hurtbox_zones"), f"{where}.hurtbox_zones"),
            # `attack_set` absent falls back to the shipped player table. The
            # shim is cached, so this does not add a parse on the normal path
            # where player.json names its set explicitly.
            attacks=attacks if attacks is not None else dict(_default_attacks()),
            speed=read_number(raw.get("speed", _PLAYER_DEFAULTS["speed"]), f"{where}.speed"),
            floor_control=read_number(
                raw.get("floor_control", _PLAYER_DEFAULTS["floor_control"]),
                f"{where}.floor_control",
            ),
            air_control=read_number(
                raw.get("air_control", _PLAYER_DEFAULTS["air_control"]), f"{where}.air_control"
            ),
            jump_height=read_number(
                raw.get("jump_height", _PLAYER_DEFAULTS["jump_height"]), f"{where}.jump_height"
            ),
            wall_jump_height=read_number(
                raw.get("wall_jump_height", _PLAYER_DEFAULTS["wall_jump_height"]),
                f"{where}.wall_jump_height",
            ),
            wall_jump_push_multiplier=read_number(
                raw.get("wall_jump_push_multiplier", _PLAYER_DEFAULTS["wall_jump_push_multiplier"]),
                f"{where}.wall_jump_push_multiplier",
            ),
            wall_jump_lock_duration=read_number(
                raw.get("wall_jump_lock_duration", _PLAYER_DEFAULTS["wall_jump_lock_duration"]),
                f"{where}.wall_jump_lock_duration",
            ),
            wall_jump_min_lock=read_number(
                raw.get("wall_jump_min_lock", _PLAYER_DEFAULTS["wall_jump_min_lock"]),
                f"{where}.wall_jump_min_lock",
            ),
            wall_slide_speed=read_number(
                raw.get("wall_slide_speed", _PLAYER_DEFAULTS["wall_slide_speed"]),
                f"{where}.wall_slide_speed",
            ),
            max_midair_jumps=read_int(
                raw.get("max_midair_jumps", _PLAYER_DEFAULTS["max_midair_jumps"]),
                f"{where}.max_midair_jumps",
            ),
            max_wall_jumps=(
                _read_wall_jumps(raw["max_wall_jumps"], f"{where}.max_wall_jumps")
                if "max_wall_jumps" in raw
                else _PLAYER_DEFAULTS["max_wall_jumps"]
            ),
            coyote_duration=read_number(
                raw.get("coyote_duration", _PLAYER_DEFAULTS["coyote_duration"]),
                f"{where}.coyote_duration",
            ),
            jump_buffer_duration=read_number(
                raw.get("jump_buffer_duration", _PLAYER_DEFAULTS["jump_buffer_duration"]),
                f"{where}.jump_buffer_duration",
            ),
            max_dash_charges=read_int(
                raw.get("max_dash_charges", _PLAYER_DEFAULTS["max_dash_charges"]),
                f"{where}.max_dash_charges",
            ),
            dash_speed=read_number(
                raw.get("dash_speed", _PLAYER_DEFAULTS["dash_speed"]), f"{where}.dash_speed"
            ),
            dash_duration=read_number(
                raw.get("dash_duration", _PLAYER_DEFAULTS["dash_duration"]),
                f"{where}.dash_duration",
            ),
            dash_penalty_duration=read_number(
                raw.get("dash_penalty_duration", _PLAYER_DEFAULTS["dash_penalty_duration"]),
                f"{where}.dash_penalty_duration",
            ),
            dash_recharge_time=read_number(
                raw.get("dash_recharge_time", _PLAYER_DEFAULTS["dash_recharge_time"]),
                f"{where}.dash_recharge_time",
            ),
            dash_gravity_mult=read_number(
                raw.get("dash_gravity_mult", _PLAYER_DEFAULTS["dash_gravity_mult"]),
                f"{where}.dash_gravity_mult",
            ),
            dash_coyote_time=read_number(
                raw.get("dash_coyote_time", _PLAYER_DEFAULTS["dash_coyote_time"]),
                f"{where}.dash_coyote_time",
            ),
            hurt_duration=read_number(
                raw.get("hurt_duration", _PLAYER_DEFAULTS["hurt_duration"]),
                f"{where}.hurt_duration",
            ),
            invincibility_duration=read_number(
                raw.get("invincibility_duration", _PLAYER_DEFAULTS["invincibility_duration"]),
                f"{where}.invincibility_duration",
            ),
            faction=str(raw.get("faction", _PLAYER_DEFAULTS["faction"])),
        )
    except (TypeError, ValueError) as exc:
        raise GameplayDataError(f"{where}: invalid player value: {exc}") from exc


def read_player_file(
    path: str | Path, attack_sets: dict[str, dict[MoveId, AttackDefinition]]
) -> PlayerConfig:
    """Load the player config block from a ``player.json`` file."""
    raw = read_json_object(path, PLAYER_VERSION)
    reject_unknown(raw, frozenset({"version", "player"}), str(path))
    return read_player_config(raw.get("player", {}), str(path), attack_sets)
