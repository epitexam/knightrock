"""Attack loading and strict validation.

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
    MoveId,
    PhaseDefinition,
    Stance,
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

MAX_VERTICAL_LUNGE = 1.0
"""Largest vertical lunge, in jump heights. 1.0 *is* a jump; above that a move
out-launches the jump that put the fighter in the air, which makes the jump the
optional move and the attack the mandatory one."""

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
    limit_x: float,
    limit_y: float,
) -> None:
    """Keyframes must be ordered, in span, and inside the sprite envelope."""
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
        if abs(keyframe.offset[0]) > limit_x or abs(keyframe.offset[1]) > limit_y:
            raise GameplayDataError(
                f"Attack {name!r} phase {phase_index} {field}: keyframe "
                f"{keyframe.frame} offset {keyframe.offset} is outside the "
                f"{ENVELOPE_MARGIN}x sprite envelope "
                f"(|x| <= {limit_x}, |y| <= {limit_y})"
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
        _validate_keyframes(name, phase_index, field, keyframes, span, limit_x, limit_y)


def _validate_attack(name: str, definition: AttackDefinition) -> None:
    """Timing rules of one attack.

    A cooldown may be shorter than the attack, or zero. It used to have to
    outlast the attack, which made every move a single blow followed by a wait:
    the basic moves of a hack and slash are paced by their own frame data and
    their cancel windows, and a cooldown is for the moves that must not be
    spammed (a special, a launcher).
    """
    last_index = len(definition.phases) - 1
    _validate_vertical_lunge(name, definition)
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


def _validate_vertical_lunge(name: str, definition: AttackDefinition) -> None:
    """Refuse a vertical lunge that cannot fire, or one without a ceiling.

    Two things can be wrong with the number, and only one of them is loud.

    A ground-only move carrying a vertical lunge is dead data: the impulse is
    applied on the airborne branch, so the field is read and discarded. That is
    a balance change someone made to a move that will never run it -- the same
    class of mistake as a self-cancel, and just as invisible.

    A multiplier above 1.0 launches the fighter higher than a jump does, which
    is the sort of number that looks fine in a diff and is not fine in a game.
    The field is a multiple of jump height precisely so that 1.0 *is* a jump,
    and the bound keeps the comparison meaningful.
    """
    lunge = definition.vertical_lunge
    if lunge and Stance.AIR not in definition.stances:
        raise GameplayDataError(
            f"Attack {name!r}: vertical_lunge {lunge} but its stances are "
            f"{[stance.value for stance in definition.stances]}, which do not include "
            "'air' — the impulse is only applied off the ground, so this is never read"
        )
    if abs(lunge) > MAX_VERTICAL_LUNGE:
        raise GameplayDataError(
            f"Attack {name!r}: vertical_lunge {lunge} exceeds {MAX_VERTICAL_LUNGE} "
            "jump heights; a move that out-jumps the jump is a launcher, not an aerial"
        )


def validate_attacks(attacks: Mapping[MoveId, AttackDefinition]) -> None:
    """Validate a whole attack table, including cross-attack cancels.

    Raises
    ------
    GameplayDataError
        A cancel references an attack outside the table, or any frame-data
        rule is violated.
    """
    names = set(attacks)
    for name, definition in attacks.items():
        unknown: set[MoveId] = set()
        for phase in definition.phases:
            unknown.update(set(phase.cancel_into) - names)
        if unknown:
            raise GameplayDataError(
                f"Attack {name!r} references unknown cancels: {', '.join(sorted(unknown))}"
            )
        _validate_cancels(name, definition, attacks)
        _validate_attack(name, definition)


def _validate_cancels(
    name: MoveId,
    definition: AttackDefinition,
    attacks: Mapping[MoveId, AttackDefinition],
) -> None:
    """Refuse a cancel that cannot fire, or one that crosses a posture.

    Two ways a ``cancel_into`` name passes the existence check and is still
    wrong:

    * it names the attack itself while the attack is still on cooldown at its
      own last frame. The cooldown gate runs before the cancel gate, so such a
      ``light_attack -> light_attack`` was accepted at load time and dead in
      play. A self-cancel on a move whose cooldown runs out within it is a
      chain (light, light, light) and is accepted.
    * it names a move whose ``stances`` do not include this one's. That was the
      ``air_attack -> light_attack`` chain: an air chain into a ground move.

    A cycle *between* different moves is deliberately not refused.
    ``light_attack`` and ``dash_attack`` cancel into each other, and that is
    ordinary: what bounds the chain is the cooldown gate, which every move clears
    before it can be thrown again. Refusing mutual cancels would have rejected a
    table that works.
    """
    _validate_follow_ups(name, definition, attacks)
    for index, phase in enumerate(definition.phases):
        for target in phase.cancel_into:
            if target == name and definition.cooldown >= definition.total_frames / FRAME_RATE:
                raise GameplayDataError(
                    f"Attack {name!r} phase {index}: cancels into itself ({target!r}), "
                    f"which its {definition.cooldown:g}s cooldown makes unreachable"
                )
            missing = set(attacks[target].stances) - set(definition.stances)
            if missing:
                raise GameplayDataError(
                    f"Attack {name!r} phase {index}: cancels into {target!r}, which is not "
                    f"reachable from {'/'.join(sorted(s.value for s in definition.stances))} "
                    f"(it needs {'/'.join(sorted(s.value for s in missing))})"
                )


def _validate_follow_ups(
    name: MoveId,
    definition: AttackDefinition,
    attacks: Mapping[MoveId, AttackDefinition],
) -> None:
    """Refuse a chain link that names nothing, or that no phase lets through.

    A follow-up is started like any move, through ``start_attack``, so it only
    fires where a phase's ``cancel_into`` allows it. One that no phase lists
    would load and never chain.
    """
    reachable = {target for phase in definition.phases for target in phase.cancel_into}
    for button, target in definition.follow_ups:
        if target not in attacks:
            raise GameplayDataError(
                f"Attack {name!r}: follow-up on {button.value!r} names unknown move {target!r}"
            )
        if target not in reachable:
            raise GameplayDataError(
                f"Attack {name!r}: follow-up on {button.value!r} is {target!r}, which no "
                "phase lists in cancel_into, so the chain could never fire"
            )


def load_attacks(combat: CombatComponent, attacks: Mapping[MoveId, AttackDefinition]) -> None:
    """Validate then register a mapping of attack definitions.

    Parameters
    ----------
    combat : CombatComponent
        The combat component to populate.
    attacks : Mapping[MoveId, AttackDefinition]
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
