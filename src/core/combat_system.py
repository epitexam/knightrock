"""
Handles attack resolution between combatants.
"""
import pygame
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.entities.entity import Entity


class CombatSystem:
    """Processes attack hit detection and applies damage/knockback."""

    def __init__(self):
        self.hit_stop_timer = 0.0

    def process_attacks(self, combat_sprites: pygame.sprite.Group, delta_time: float) -> None:
        """Check all active attack boxes against all targets."""
        if self.hit_stop_timer > 0:
            return

        for attacker in combat_sprites:
            if not attacker.combat.is_attacking or not attacker.combat.attack_box:
                continue
            phase = attacker.combat.current_phase
            if phase is None:
                continue

            for target in combat_sprites:
                if attacker is target:
                    continue
                if target in attacker.combat.targets_hit:
                    continue

                if attacker.combat.attack_box.colliderect(target.hurtbox):
                    target.combat.take_damage(
                        amount=phase.damage,
                        source_center_x=attacker.hitbox.centerx,
                        knockback=phase.knockback,
                    )
                    attacker.combat.targets_hit.add(target)
                    self.hit_stop_timer = 0.05 + (phase.damage * 0.002)

    def update_timer(self, delta_time: float) -> None:
        if self.hit_stop_timer > 0:
            self.hit_stop_timer -= delta_time
            if self.hit_stop_timer < 0:
                self.hit_stop_timer = 0.0

    @property
    def in_hit_stop(self) -> bool:
        return self.hit_stop_timer > 0