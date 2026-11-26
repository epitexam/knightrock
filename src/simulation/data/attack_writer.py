"""Serialization of attack frame data back to its JSON shape.

The loader lives in :mod:`src.data.attacks`; this module owns the inverse
direction. Keeping them apart means the strict JSON readers do not carry the
round-trip writer, and the writer's byte-exact output has a single home.
``src.data.attacks`` re-exports these names for existing callers.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.simulation.combat.frame_data import AttackDefinition, HitboxKeyframe, HitboxSpec, MoveId
from src.simulation.combat.shapes import AnchorKind, EasingKind, ShapeKind

# The shipped table is v2; writing v1 by default would silently rewrite every
# exported move into the older flat dialect on the next round-trip.
ATTACKS_VERSION = 2


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
                    "tags": list(phase.hit.tags),
                    **({"flinch": True} if phase.hit.flinch else {}),
                    **({"hit_stop": phase.hit.hit_stop} if phase.hit.hit_stop is not None else {}),
                    **({"stun": phase.hit.stun} if phase.hit.stun else {}),
                    **({"execute": True} if phase.hit.execute else {}),
                },
                "extra_hitboxes": [_hitbox_spec_to_dict(spec) for spec in phase.extra_hitboxes],
                "hitbox_keyframes": [
                    _keyframe_to_dict(keyframe) for keyframe in phase.hitbox_keyframes
                ],
                "reset_targets": phase.reset_targets,
                "cancel_into": list(phase.cancel_into),
                **({"cancel_on_hit": True} if phase.cancel_on_hit else {}),
                **({"launches": phase.launches} if phase.launches else {}),
                **({"auto_into": phase.auto_into} if phase.auto_into else {}),
            }
            for phase in definition.phases
        ],
        "cooldown": definition.cooldown,
        "stances": [stance.value for stance in definition.stances],
        "animation": definition.animation,
        "lock_direction": definition.lock_direction,
        "combo_reset": definition.combo_reset,
        "chargeable": definition.chargeable,
        "max_charge_time": definition.max_charge_time,
        "charge_move_multiplier": definition.charge_move_multiplier,
        "uninterruptible": definition.uninterruptible,
        **({"invincible": True} if definition.invincible else {}),
        "lunge_speed_multiplier": definition.lunge_speed_multiplier,
        "vertical_lunge": definition.vertical_lunge,
        "attack_move_multiplier": definition.attack_move_multiplier,
        **(
            {"follow_ups": {button.value: move for button, move in definition.follow_ups}}
            if definition.follow_ups
            else {}
        ),
    }


def attack_definition_to_v2_dict(definition: AttackDefinition) -> dict[str, Any]:
    """Serialize an attack with the canonical ``hitboxes`` list."""
    raw = attack_definition_to_dict(definition)
    for phase, phase_data in zip(definition.phases, raw["phases"], strict=True):
        hitboxes = [_hitbox_spec_to_dict(spec) for spec in phase.boxes]
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
    attack_sets: Mapping[str, Mapping[MoveId, AttackDefinition]],
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
    attack_sets: Mapping[str, Mapping[MoveId, AttackDefinition]],
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
