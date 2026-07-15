"""
Hitbox position tracking for active attack phases.

The ``HitboxManager`` calculates and caches the attack hitbox rectangle
based on the current phase's frame data and the attacker's position.
The hitbox only exists during the ACTIVE sub-state of each phase.
"""

from __future__ import annotations

import pygame

from src.combat.attack_state import AttackStateMachine
from src.combat.combatant_protocol import Combatant
from src.combat.frame_data import PhaseDefinition


class HitboxManager:
    """Manages the attack hitbox position and lifecycle.

    The hitbox rectangle is recalculated every update.  It is set to
    ``None`` whenever the attack is not in the ACTIVE sub-state.

    Parameters
    ----------
    entity : Combatant
        The entity that owns this manager.  Used to read ``hitbox``
        centre and ``facing_right`` for offset calculations.

    Attributes
    ----------
    rect : pygame.FRect | None
        The current attack hitbox, or ``None`` if inactive.
    """

    def __init__(self, entity: Combatant) -> None:
        self._entity: Combatant = entity
        self.rect: pygame.FRect | None = None

    def update(self, state: AttackStateMachine) -> None:
        """Recalculate the hitbox based on the current attack state.

        The hitbox is only present during the ACTIVE sub-state.  During
        STARTUP, RECOVERY, and IDLE the hitbox is cleared.

        Parameters
        ----------
        state : AttackStateMachine
            The current attack state machine, used to determine the
            active phase and facing direction.
        """
        if not state.is_active or state.attack_name is None:
            self.rect = None
            return

        phase = state.current_phase_def
        if phase is None:
            self.rect = None
            return

        facing_right = state.effective_facing
        if facing_right is None:
            facing_right = self._entity.facing_right

        self.rect = self._calculate_rect(phase, facing_right)

    def clear(self) -> None:
        """Remove the hitbox immediately (e.g. on hit-stun)."""
        self.rect = None

    def _calculate_rect(
        self, phase: PhaseDefinition, facing_right: bool
    ) -> pygame.FRect:
        """Calculate the hitbox rectangle for the given phase and facing.

        Parameters
        ----------
        phase : PhaseDefinition
            The current active phase containing hitbox size and offset.
        facing_right : bool
            Whether the attacker is facing right.

        Returns
        -------
        pygame.FRect
            The positioned hitbox rectangle.
        """
        rect = pygame.FRect((0, 0), phase.hitbox_size)
        offset_x, offset_y = phase.hitbox_offset
        if not facing_right:
            offset_x = -offset_x
        rect.center = (
            self._entity.hitbox.centerx + offset_x,
            self._entity.hitbox.centery + offset_y,
        )
        return rect