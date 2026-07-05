"""
Component managing the combat state, attacks, combos, and charging of an entity.
"""
import weakref
from typing import Any
import pygame

from src.combat.attack_types import AttackPhase, AttackSequence, KnockbackConfig
from src.core.settings import Combat as CombatSettings
from src.combat.combatant_protocol import Combatant


class CombatComponent:
    """Represents the combat state and mechanics of an entity."""

    def __init__(self, entity: Combatant) -> None:
        self.entity = entity
        self.attacks: dict[str, AttackSequence] = {}
        self.cooldowns: dict[str, float] = {}

        self.current_attack: str | None = None
        self.current_phase_index: int = 0
        self.attack_timer: float = 0.0
        self.attack_box: pygame.FRect | None = None
        self.targets_hit: weakref.WeakSet[Any] = weakref.WeakSet()

        self.is_hurt: bool = False
        self.hurt_timer: float = 0.0
        self._locked_facing_right: bool | None = None
        self.charge_multiplier: float = 1.0

        self.combo_count: int = 0
        self.combo_timer: float = 0.0
        self.last_attack_name: str | None = None

        self.is_charging: bool = False
        self.charge_timer: float = 0.0
        self.charging_attack_name: str | None = None

    def add_attack(self, name: str, sequence: AttackSequence) -> None:
        self.attacks[name] = sequence
        self.cooldowns[name] = 0.0

    @property
    def is_attacking(self) -> bool:
        return self.current_attack is not None

    @property
    def current_phase(self) -> AttackPhase | None:
        if not self.current_attack:
            return None
        return self.attacks[self.current_attack].phases[self.current_phase_index]

    def on_hit(self, duration: float | None = None) -> None:
        self.is_hurt = True
        self.hurt_timer = duration if duration is not None else CombatSettings.HURT_DURATION
        self._end_attack()
        self.is_charging = False
        self.charge_timer = 0.0
        self.charging_attack_name = None

    def take_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None:
        self.entity.receive_damage(amount, source_center_x, knockback)

    def start_charge(self, name: str) -> bool:
        if self.is_attacking or self.is_hurt or self.is_charging:
            return False
        if name not in self.attacks or not self.attacks[name].chargeable:
            return False
        if self.cooldowns[name] > 0:
            return False
        self.is_charging = True
        self.charge_timer = 0.0
        self.charging_attack_name = name
        return True

    def release_charge(self, facing_right: bool) -> bool:
        if not self.is_charging or not self.charging_attack_name:
            return False
        name = self.charging_attack_name
        sequence = self.attacks[name]
        max_time = max(sequence.max_charge_time, 0.001)
        charge_mult = 1.0 + (self.charge_timer / max_time)
        self.is_charging = False
        self.charge_timer = 0.0
        self.charging_attack_name = None
        return self.start_attack(name, facing_right, charge_mult)

    def start_attack(self, name: str, facing_right: bool, charge_multiplier: float = 1.0) -> bool:
        if self.is_attacking or self.is_hurt or self.is_charging:
            return False
        if name not in self.attacks:
            return False
        if self.cooldowns[name] > 0:
            return False

        sequence = self.attacks[name]

        if sequence.combo_reset:
            self.combo_count = 0
            self.combo_timer = 0.0
        else:
            if self.combo_timer > 0:
                self.combo_count += 1
            else:
                self.combo_count = 1
            self.combo_timer = CombatSettings.COMBO_WINDOW

        self.last_attack_name = name
        self.current_attack = name
        self.current_phase_index = 0
        self.cooldowns[name] = sequence.cooldown
        self.targets_hit.clear()
        self._locked_facing_right = facing_right if sequence.lock_direction else None
        self.charge_multiplier = charge_multiplier

        phase = sequence.phases[0]
        self.attack_timer = phase.duration
        self.attack_box = pygame.FRect((0, 0), phase.size)
        self._update_hitbox_position(self._effective_direction(facing_right))
        return True

    def update(self, delta_time: float, facing_right: bool) -> None:
        if self.hurt_timer > 0:
            self.hurt_timer -= delta_time
            if self.hurt_timer <= 0:
                self.is_hurt = False

        for name in self.cooldowns:
            if self.cooldowns[name] > 0:
                self.cooldowns[name] -= delta_time

        if self.combo_timer > 0:
            self.combo_timer -= delta_time
            if self.combo_timer <= 0:
                self.combo_count = 0

        if self.is_charging and self.charging_attack_name:
            sequence = self.attacks[self.charging_attack_name]
            self.charge_timer = min(
                self.charge_timer + delta_time, sequence.max_charge_time)

        if self.current_attack:
            self.attack_timer -= delta_time
            if self.attack_timer <= 0:
                self._advance_phase(facing_right)
            else:
                self._update_hitbox_position(
                    self._effective_direction(facing_right))

    def _effective_direction(self, facing_right: bool) -> bool:
        return self._locked_facing_right if self._locked_facing_right is not None else facing_right

    def _advance_phase(self, facing_right: bool) -> None:
        if not self.current_attack:
            return
        sequence = self.attacks[self.current_attack]
        next_index = self.current_phase_index + 1
        if next_index >= len(sequence.phases):
            self._end_attack()
            return
        self.current_phase_index = next_index
        phase = sequence.phases[next_index]
        if phase.reset_targets:
            self.targets_hit.clear()
        self.attack_timer = phase.duration
        self.attack_box = pygame.FRect((0, 0), phase.size)
        self._update_hitbox_position(self._effective_direction(facing_right))

    def _end_attack(self) -> None:
        self.current_attack = None
        self.current_phase_index = 0
        self.attack_timer = 0.0
        self.attack_box = None
        self.targets_hit.clear()
        self._locked_facing_right = None
        self.charge_multiplier = 1.0

    def _update_hitbox_position(self, facing_right: bool) -> None:
        if not self.attack_box or not self.current_attack:
            return
        phase = self.attacks[self.current_attack].phases[self.current_phase_index]
        offset_x, offset_y = phase.offset
        if not facing_right:
            offset_x = -offset_x
        self.attack_box.center = (
            self.entity.hitbox.centerx + offset_x,
            self.entity.hitbox.centery + offset_y,
        )


class NullCombatComponent:
    """Null object implementation for entities without combat capabilities."""

    def __init__(self) -> None:
        self.is_attacking = False
        self.is_hurt = False
        self.current_attack = None
        self.current_phase_index = 0
        self.attack_timer = 0.0
        self.attack_box = None
        self.targets_hit = set()
        self.hurt_timer = 0.0
        self._locked_facing_right = None
        self.charge_multiplier = 1.0
        self.combo_count = 0
        self.combo_timer = 0.0
        self.last_attack_name = None
        self.is_charging = False
        self.charge_timer = 0.0
        self.charging_attack_name = None

    def add_attack(self, name: str, sequence: AttackSequence) -> None: pass
    def on_hit(self, duration: float | None = None) -> None: pass
    def start_charge(self, name: str) -> bool: return False
    def release_charge(self, facing_right: bool) -> bool: return False
    def start_attack(self, name: str, facing_right: bool,
                     charge_multiplier: float = 1.0) -> bool: return False

    def _end_attack(self) -> None: pass

    def update(self, delta_time: float, facing_right: bool) -> None: pass

    def take_damage(self, amount: int, source_center_x: float | None = None,
                    knockback: KnockbackConfig | None = None) -> None: pass

    @property
    def current_phase(self) -> AttackPhase | None:
        return None
