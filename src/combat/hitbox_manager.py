"""Lifecycle and positioning of active offensive hitboxes."""

from __future__ import annotations

import pygame

from src.combat.attack_state import AttackStateMachine
from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import PhaseDefinition


class HitboxManager:
    """Own the offensive rectangles of an active attack phase.

    ``rect`` stays the primary offensive rectangle (legacy single-box
    attacks expose exactly one box). ``rects`` is the full
    pool — primary box first, then one slot per
    ``PhaseDefinition.extra_hitboxes`` entry. Both views share the same
    rectangles: ``rects[0] is rect`` whenever a box is live.
    """

    def __init__(self, entity: Combatant) -> None:
        self._entity: Combatant = entity
        self.rect: pygame.FRect | None = None
        self._pool: list[pygame.FRect] = []

    @property
    def rects(self) -> tuple[pygame.FRect, ...]:
        """Live offensive rectangles: primary box first, then extras."""
        return tuple(self._pool)

    def update(self, state: AttackStateMachine) -> None:
        """Synchronize geometry from attack state and owner position."""
        if not state.is_active or state.attack_name is None:
            self.clear()
            return

        phase = state.current_phase_def
        if phase is None:
            self.clear()
            return

        facing_right = state.effective_facing
        if facing_right is None:
            facing_right = self._entity.facing_right
        self._position_rects(phase, facing_right)

    def clear(self) -> None:
        """Remove offensive geometry immediately."""
        self.rect = None
        self._pool.clear()

    def _position_rects(self, phase: PhaseDefinition, facing_right: bool) -> None:
        """Create or reposition every rectangle without per-tick allocation."""
        specs = (
            (phase.hitbox_size, phase.hitbox_offset),
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
