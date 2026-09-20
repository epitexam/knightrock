"""Lifecycle and positioning of active offensive hitboxes."""

from __future__ import annotations

import pygame

from src.combat.attack_state import AttackStateMachine
from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import PhaseDefinition
from src.combat.sweep import swept_box


class HitboxManager:
    """Own the offensive rectangles of an active attack phase.

    ``rect`` stays the primary offensive rectangle (legacy single-box
    attacks expose exactly one box). ``rects`` is the full
    pool — primary box first, then one slot per
    ``PhaseDefinition.extra_hitboxes`` entry. Both views share the same
    rectangles: ``rects[0] is rect`` whenever a box is live.

    P1 sweep: ``_prev_pool`` holds the geometry captured at the previous
    tick boundary (``capture_origin``), the sole other writers of which
    are the ``start_attack`` seed (D1) and ``clear`` (attack end).
    ``update`` never touches it: positioning is pure and idempotent, so
    the double sync (``Entity.update`` + gameplay loop) is harmless.
    """

    def __init__(self, entity: Combatant) -> None:
        self._entity: Combatant = entity
        self.rect: pygame.FRect | None = None
        self._pool: list[pygame.FRect] = []
        self._prev_pool: list[pygame.FRect] = []

    @property
    def rects(self) -> tuple[pygame.FRect, ...]:
        """Live offensive rectangles: primary box first, then extras."""
        return tuple(self._pool)

    @property
    def prev_rects(self) -> tuple[pygame.FRect, ...]:
        """Copies of the rectangles captured at the previous tick boundary."""
        return tuple(rect.copy() for rect in self._prev_pool)

    @property
    def swept_rects(self) -> tuple[pygame.FRect, ...]:
        """Per-index swept rectangles between the captured origin and now.

        An index without a captured origin (spawn, resize) or whose
        displacement is out of the ``Combat`` sweep bounds yields ``cur``
        (D1/D4); otherwise the union of prev and cur.
        """
        return tuple(
            swept_box(
                self._prev_pool[index] if index < len(self._prev_pool) else None,
                rect,
            )
            for index, rect in enumerate(self._pool)
        )

    def update(self, state: AttackStateMachine) -> None:
        """Synchronize geometry from attack state and owner position.

        Geometry is live during startup *and* active: the animated curve
        starts at phase frame 0 (windup), so the debug overlay and the
        per-frame sweep both track the swing from its first frame.
        Recovery clears the box, as before.
        """
        if not state.is_attacking or state.attack_name is None:
            self.clear()
            return

        phase = state.current_phase_def
        if phase is None:
            self.clear()
            return

        facing_right = state.effective_facing
        if facing_right is None:
            facing_right = self._entity.facing_right
        self._position_rects(phase, facing_right, state.animation_frame)

    def clear(self) -> None:
        """Remove offensive geometry immediately (end of attack)."""
        self.rect = None
        self._pool.clear()
        self._prev_pool.clear()

    def capture_origin(self) -> None:
        """Copy the live pool as the sweep origin of the next tick.

        Called once per tick at the frontier, by the gameplay loop,
        before any movement or attack start of the tick. Deep copy: the
        pool rectangles are repositioned in place afterwards.
        """
        self._prev_pool = [rect.copy() for rect in self._pool]

    def clear_origin(self) -> None:
        """Forget the sweep origin (rollback hygiene, re-derived on next capture)."""
        self._prev_pool.clear()

    def _position_rects(self, phase: PhaseDefinition, facing_right: bool, frame: int) -> None:
        """Create or reposition every rectangle without per-tick allocation.

        The primary box follows the phase's animated curve
        (``hitbox_at``); extra boxes stay static by design (#1 scope).
        """
        specs = (
            (phase.hitbox_at(frame)),
            *((spec.size, spec.offset) for spec in phase.extra_hitboxes),
        )
        while len(self._pool) < len(specs):
            self._pool.append(pygame.FRect(0, 0, 0, 0))
        while len(self._pool) > len(specs):
            self._pool.pop()
        for rect, (size, offset) in zip(self._pool, specs, strict=True):
            rect.size = size
            offset_x, offset_y = offset
            if not facing_right:
                offset_x = -offset_x
            rect.center = (
                self._entity.hitbox.centerx + offset_x,
                self._entity.hitbox.centery + offset_y,
            )
        self.rect = self._pool[0]
