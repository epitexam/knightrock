"""
System responsible for processing combat interactions, hit detection, and damage resolution.
"""
import pygame
from typing import TYPE_CHECKING

from src.core.settings import Combat as CombatSettings
from src.combat.attack_types import AttackPhase

if TYPE_CHECKING:
    from src.entities.entity import Entity


class CombatSystem:
    """Processes attack hit detection and applies damage, knockback, and status effects."""

    def __init__(self) -> None:
        self.hit_stop_timer: float = 0.0

    def process_attacks(self, combat_sprites: pygame.sprite.Group) -> None:
        """Checks all active attack boxes against all targets and resolves hits."""
        if self.hit_stop_timer > 0:
            return

        for attacker in combat_sprites:
            if not attacker.combat.is_attacking or not attacker.combat.attack_box:
                continue

            phase = attacker.combat.current_phase
            if phase is None:
                continue

            attacker_faction = getattr(attacker, 'faction', None)
            attack_box = attacker.combat.attack_box

            for target in combat_sprites:
                if attacker is target:
                    continue

                target_faction = getattr(target, 'faction', None)
                if attacker_faction is not None and attacker_faction == target_faction:
                    continue

                if target in attacker.combat.targets_hit:
                    continue

                if not attack_box.colliderect(target.hurtbox):
                    continue

                self._resolve_hit(attacker, target, phase)
                attacker.combat.targets_hit.add(target)
                hitstop_duration = (
                    CombatSettings.HITSTOP_BASE
                    + (phase.damage * CombatSettings.HITSTOP_DAMAGE_FACTOR)
                )
                self.hit_stop_timer = hitstop_duration
                attacker.combat.hit_pause_timer = hitstop_duration
                target.combat.hit_pause_timer = hitstop_duration

    def _resolve_hit(self, attacker: "Entity", target: "Entity", phase: AttackPhase) -> None:
        """Calculates and applies damage, stagger, and finisher effects to the target."""

        charge_mult = attacker.combat.charge_multiplier

        type_mult = 1.0
        if hasattr(target, 'get_damage_modifier'):
            type_mult = target.get_damage_modifier(phase.damage_type)

        final_damage = int(phase.damage * charge_mult * type_mult)

        target_has_super_armor = getattr(target, 'has_super_armor', False)

        if target_has_super_armor and not phase.super_armor_break:
            target.combat.take_damage(
                final_damage, attacker.hitbox.centerx, None)
        else:
            if target_has_super_armor and phase.super_armor_break and hasattr(target, 'break_super_armor'):
                target.break_super_armor()

            target.combat.take_damage(
                final_damage, attacker.hitbox.centerx, phase.knockback)

            if phase.stagger > 0 and hasattr(target, "stagger"):
                target.stagger(phase.stagger)

        if phase.is_finisher and target.health <= target.max_health * 0.2:
            target.combat.take_damage(
                int(target.health), attacker.hitbox.centerx, phase.knockback)

    def update_timer(self, delta_time: float) -> None:
        """Updates the hit-stop timer."""
        if self.hit_stop_timer > 0:
            self.hit_stop_timer -= delta_time
            if self.hit_stop_timer < 0:
                self.hit_stop_timer = 0.0

    @property
    def in_hit_stop(self) -> bool:
        """Indicates if the game is currently in hit-stop."""
        return self.hit_stop_timer > 0
