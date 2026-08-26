"""Lifecycle and positioning of active offensive hitboxes."""

from __future__ import annotations

import pygame

from src.combat.attack_state import AttackStateMachine
from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import PhaseDefinition


class HitboxManager:
    """Own the single offensive rectangle of an active attack phase."""

    def __init__(self, entity: Combatant) -> None:
        self._entity: Combatant = entity
        self.rect: pygame.FRect | None = None

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
        self._position_rect(phase, facing_right)

    def clear(self) -> None:
        """Remove offensive geometry immediately."""
        self.rect = None

    def _position_rect(
        self, phase: PhaseDefinition, facing_right: bool
    ) -> None:
        """Create or reposition the rectangle without per-tick allocation."""
        if self.rect is None:
            self.rect = pygame.FRect((0, 0), phase.hitbox_size)
        else:
            self.rect.size = phase.hitbox_size

        offset_x, offset_y = phase.hitbox_offset
        if not facing_right:
            offset_x = -offset_x
        self.rect.center = (
            self._entity.hitbox.centerx + offset_x,
            self._entity.hitbox.centery + offset_y,
        )
