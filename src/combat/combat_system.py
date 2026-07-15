"""
System responsible for processing combat interactions, hit detection, and timing.

The ``CombatSystem`` iterates over all combatants, checks for hitbox collisions
during active attack frames, delegates hit resolution to ``HitResolver``, and
manages the global hit-stop (freeze frame) timer for impact emphasis.
"""

import pygame
from typing import TYPE_CHECKING

from src.core.settings import Combat as CombatSettings
from src.combat.frame_data import PhaseState
from src.combat.hit_resolver import HitResolver

if TYPE_CHECKING:
    from src.entities.entity import Entity


class CombatSystem:
    """Processes attack hit detection and manages hit-stop timing.

    Attributes
    ----------
    hit_stop_timer : float
        Remaining time in seconds for the current hit-stop effect.
    """

    def __init__(self) -> None:
        self.hit_stop_timer: float = 0.0

    def process_attacks(self, combat_sprites: pygame.sprite.Group) -> None:
        """Check all active attack boxes against valid targets and resolve hits.

        Iterates through all entities in ``combat_sprites``.  If an entity
        is attacking and in the ACTIVE sub-state, its attack box is tested
        against the hurtboxes of entities from different factions.  Valid
        hits are forwarded to ``HitResolver.resolve``.

        Parameters
        ----------
        combat_sprites : pygame.sprite.Group
            The group containing all entities participating in combat.
        """
        if self.hit_stop_timer > 0:
            return

        for attacker in combat_sprites:
            if getattr(attacker, 'is_dead', False):
                continue

            combat = attacker.combat

            if not combat.state.is_active or combat.attack_box is None:
                continue

            phase = combat.current_phase
            if phase is None:
                continue

            attacker_faction = getattr(attacker, 'faction', None)
            attack_box = combat.attack_box

            for target in combat_sprites:
                if attacker is target:
                    continue
                if target.is_dead:
                    continue

                target_faction = getattr(target, 'faction', None)
                if attacker_faction == target_faction:
                    continue

                if target in combat.targets_hit:
                    continue

                if not attack_box.colliderect(target.hurtbox):
                    continue

                HitResolver.resolve(
                    attacker=attacker,
                    target=target,
                    hit=phase.hit,
                    charge_multiplier=combat.charge_multiplier,
                )

                combat.targets_hit.add(target)

                hitstop_duration = (
                    CombatSettings.HITSTOP_BASE
                    + (phase.hit.damage * CombatSettings.HITSTOP_DAMAGE_FACTOR)
                )
                self.hit_stop_timer = max(
                    self.hit_stop_timer, hitstop_duration)

    def update_timer(self, delta_time: float) -> None:
        """Tick the hit-stop timer.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        """
        if self.hit_stop_timer > 0:
            self.hit_stop_timer -= delta_time
            if self.hit_stop_timer < 0:
                self.hit_stop_timer = 0.0

    @property
    def in_hit_stop(self) -> bool:
        """Indicates if the game is currently in hit-stop."""
        return self.hit_stop_timer > 0
