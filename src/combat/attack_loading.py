"""Attack loading and strict validation (P4.2).

``load_attacks`` is the single entry point for attack definitions (builtin
tables and gameplay JSON both go through it), so it is also where malformed
frame data must fail loudly instead of silently producing a dead attack:

- box size strictly positive, offset inside the documented sprite envelope
  (``ENVELOPE_MARGIN`` x ``SPRITE_SIZE``);
- keyframes inside ``0..startup + active``, strictly increasing;
- a configured cooldown at least as long as the attack itself;
- ``cancel_into`` referencing a registered attack.

Advisory (``warnings.warn``): an intermediate multi-hit phase that does not
reset its already-hit targets, which blocks the next phase from re-hitting.
Errors are :class:`GameplayDataError` and always name the attack, the
phase index and the field at fault — never a silent fallback.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator, Mapping

from src.combat.combat_component import CombatComponent
from src.combat.frame_data import (
    FRAME_RATE,
    AttackDefinition,
    HitboxKeyframe,
    PhaseDefinition,
)
from src.data.errors import GameplayDataError

__all__ = [
    "ENVELOPE_MARGIN",
    "SPRITE_SIZE",
    "load_attacks",
    "validate_attacks",
]

SPRITE_SIZE = (40.0, 48.0)
"""Reference sprite size (see ``frame_data``) used by the validation envelope."""

ENVELOPE_MARGIN = 2.0
"""Allowed box reach, as a multiple of ``SPRITE_SIZE``, from the owner center."""

_BoxEntry = tuple[str, tuple[float, float], tuple[float, float], tuple[HitboxKeyframe, ...]]


def _box_entries(phase: PhaseDefinition) -> Iterator[_BoxEntry]:
    """Yield ``(field, size, offset, keyframes)`` for every box of a phase."""
    yield "hitbox", phase.hitbox_size, phase.hitbox_offset, phase.hitbox_keyframes
    for index, spec in enumerate(phase.extra_hitboxes):
        yield f"extra_hitboxes[{index}]", spec.size, spec.offset, spec.keyframes


def _validate_keyframes(
    name: str,
    phase_index: int,
    field: str,
    keyframes: tuple[HitboxKeyframe, ...],
    span: int,
) -> None:
    """Keyframes must be strictly increasing and inside the phase span."""
    previous = -1
    for keyframe in keyframes:
        if keyframe.frame <= previous:
            raise GameplayDataError(
                f"Attack {name!r} phase {phase_index} {field}: keyframes must use "
                f"strictly increasing frames, got {keyframe.frame} after {previous}"
            )
        if keyframe.frame > span:
            raise GameplayDataError(
                f"Attack {name!r} phase {phase_index} {field}: keyframe "
                f"{keyframe.frame} is outside the startup-to-active span 0..{span}"
            )
        previous = keyframe.frame


def _validate_phase(name: str, phase_index: int, phase: PhaseDefinition) -> None:
    """Box geometry of one phase: positive size, in-envelope offset, keyframes."""
    span = phase.startup_frames + phase.active_frames
    limit_x = ENVELOPE_MARGIN * SPRITE_SIZE[0]
    limit_y = ENVELOPE_MARGIN * SPRITE_SIZE[1]
    for field, size, offset, keyframes in _box_entries(phase):
        if not (size[0] > 0 and size[1] > 0):
            raise GameplayDataError(
                f"Attack {name!r} phase {phase_index} {field}: size {size} must be "
                "strictly positive on both axes"
            )
        if abs(offset[0]) > limit_x or abs(offset[1]) > limit_y:
            raise GameplayDataError(
                f"Attack {name!r} phase {phase_index} {field}: offset {offset} is "
                f"outside the {ENVELOPE_MARGIN}x sprite envelope "
                f"(|x| <= {limit_x}, |y| <= {limit_y})"
            )
        _validate_keyframes(name, phase_index, field, keyframes, span)


def _validate_attack(name: str, definition: AttackDefinition) -> None:
    """Timing rules of one attack."""
    duration = definition.total_frames / FRAME_RATE
    if definition.cooldown < duration:
        raise GameplayDataError(
            f"Attack {name!r}: cooldown {definition.cooldown:.3f}s is shorter than the "
            f"attack duration {duration:.3f}s ({definition.total_frames} frames at "
            f"{FRAME_RATE} Hz)"
        )
    last_index = len(definition.phases) - 1
    for index, phase in enumerate(definition.phases):
        _validate_phase(name, index, phase)
        if index < last_index and not phase.reset_targets:
            warnings.warn(
                f"Attack {name!r} phase {index}: reset_targets is False on an "
                "intermediate phase — an already-hit target cannot be hit again "
                "by the next phase",
                UserWarning,
                stacklevel=2,
            )


def validate_attacks(attacks: Mapping[str, AttackDefinition]) -> None:
    """Validate a whole attack table, including cross-attack cancels.

    Raises
    ------
    GameplayDataError
        A cancel references an attack outside the table, or any frame-data
        rule is violated.
    """
    names = set(attacks)
    for name, definition in attacks.items():
        unknown: set[str] = set()
        for phase in definition.phases:
            unknown.update(set(phase.cancel_into) - names)
        if unknown:
            raise GameplayDataError(
                f"Attack {name!r} references unknown cancels: {', '.join(sorted(unknown))}"
            )
        _validate_attack(name, definition)


def load_attacks(
    combat: CombatComponent, attacks: Mapping[str, AttackDefinition]
) -> None:
    """Validate then register a mapping of attack definitions.

    Parameters
    ----------
    combat : CombatComponent
        The combat component to populate.
    attacks : Mapping[str, AttackDefinition]
        A dictionary-like object mapping attack names to their definitions.

    Raises
    ------
    GameplayDataError
        Any frame-data rule above is violated; the message names the attack,
        the phase index and the field at fault.
    """
    validate_attacks(attacks)
    for name, definition in attacks.items():
        combat.add_attack(name, definition)
