import weakref
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pygame


@dataclass
class AttackPhase:
    size: tuple[float, float]
    offset: tuple[float, float]
    damage: int
    duration: float
    reset_targets: bool = True


@dataclass
class AttackSequence:
    phases: List[AttackPhase]
    cooldown: float
    lock_direction: bool = False


class CombatComponent:
    def __init__(self, entity: Any) -> None:
        self.entity = entity
        self.attacks: Dict[str, AttackSequence] = {}
        self.cooldowns: Dict[str, float] = {}

        self.current_attack: str | None = None
        self.current_phase_index: int = 0
        self.attack_timer: float = 0.0
        self.attack_box: pygame.FRect | None = None
        self.targets_hit: weakref.WeakSet[Any] = weakref.WeakSet()

        self.is_hurt: bool = False
        self.hurt_timer: float = 0.0
        self.contact_damage: int = 0

        self._locked_facing_right: Optional[bool] = None

    def add_attack(self, name: str, sequence: AttackSequence) -> None:
        self.attacks[name] = sequence
        self.cooldowns[name] = 0.0

    @property
    def is_attacking(self) -> bool:
        return self.current_attack is not None

    @property
    def current_phase(self) -> Optional[AttackPhase]:
        attack_name = self.current_attack
        if not attack_name:
            return None
        return self.attacks[attack_name].phases[self.current_phase_index]

    def take_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback_power: tuple[float, float] = (250.0, -150.0),
    ) -> None:
        is_blocking = (
            hasattr(self.entity, "state_machine")
            and self.entity.state_machine.current_state_name == "block"
        )

        if is_blocking:
            self.entity.block_stamina -= amount * 0.05
            if source_center_x is not None:
                direction = 1.0 if self.entity.hitbox.centerx >= source_center_x else -1.0
                self.entity.velocity.x = (knockback_power[0] * 0.3) * direction
            print("Hit blocked!")
            return

        self.is_hurt = True
        self.hurt_timer = 0.4
        self._end_attack()

        if source_center_x is not None:
            direction = 1.0 if self.entity.hitbox.centerx >= source_center_x else -1.0
            self.entity.velocity.x = knockback_power[0] * direction
            self.entity.velocity.y = knockback_power[1]
        else:
            if hasattr(self.entity, "facing_right"):
                direction = 1.0 if self.entity.facing_right else -1.0
                self.entity.velocity.x = knockback_power[0] * direction
            else:
                self.entity.velocity.x = knockback_power[0]
            self.entity.velocity.y = knockback_power[1]

    def start_attack(self, name: str, facing_right: bool) -> bool:
        if self.is_attacking or self.is_hurt:
            return False
        if name not in self.attacks:
            return False
        if self.cooldowns[name] > 0:
            return False

        sequence = self.attacks[name]
        self.current_attack = name
        self.current_phase_index = 0
        self.cooldowns[name] = sequence.cooldown
        self.targets_hit.clear()

        self._locked_facing_right = facing_right if sequence.lock_direction else None

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

        if self.current_attack:
            self.attack_timer -= delta_time
            if self.attack_timer <= 0:
                self._advance_phase(facing_right)
            else:
                self._update_hitbox_position(self._effective_direction(facing_right))

    def _effective_direction(self, facing_right: bool) -> bool:
        return self._locked_facing_right if self._locked_facing_right is not None else facing_right

    def _advance_phase(self, facing_right: bool) -> None:
        attack_name = self.current_attack
        if not attack_name:
            return
        sequence = self.attacks[attack_name]
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

    def _update_hitbox_position(self, facing_right: bool) -> None:
        attack_name = self.current_attack
        if not self.attack_box or not attack_name:
            return

        phase = self.attacks[attack_name].phases[self.current_phase_index]
        offset_x, offset_y = phase.offset

        if not facing_right:
            offset_x = -offset_x

        self.attack_box.center = (
            self.entity.hitbox.centerx + offset_x,
            self.entity.hitbox.centery + offset_y,
        )
        