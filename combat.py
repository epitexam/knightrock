import weakref
from dataclasses import dataclass
from typing import Any, Dict

import pygame


@dataclass
class AttackData:
    """Structure defining the unique characteristics of an attack."""

    size: tuple[float, float]
    offset: tuple[float, float]
    damage: int
    duration: float
    cooldown: float


class CombatComponent:
    """
    A modular component that attaches to any combat-capable entity.
    Manages attack hitboxes, animation states, cooldowns, and hurt states.
    """

    def __init__(self, entity: Any) -> None:
        self.entity = entity
        self.attacks: Dict[str, AttackData] = {}
        self.cooldowns: Dict[str, float] = {}

        self.current_attack: str | None = None
        self.attack_timer: float = 0.0
        self.attack_box: pygame.FRect | None = None
        self.targets_hit: weakref.WeakSet[Any] = weakref.WeakSet()

        self.is_hurt: bool = False
        self.hurt_timer: float = 0.0
        self.contact_damage: int = 0

    def add_attack(self, name: str, data: AttackData) -> None:
        self.attacks[name] = data
        self.cooldowns[name] = 0.0

    @property
    def is_attacking(self) -> bool:
        return self.current_attack is not None

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
                direction = (
                    1.0 if self.entity.hitbox.centerx >= source_center_x else -1.0
                )
                self.entity.velocity.x = (knockback_power[0] * 0.3) * direction
            print("Hit blocked!")
            return

        self.is_hurt = True
        self.hurt_timer = 0.4

        self.current_attack = None
        self.attack_timer = 0.0
        self.attack_box = None
        self.targets_hit.clear()

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

        attack = self.attacks[name]
        self.current_attack = name
        self.attack_timer = attack.duration
        self.cooldowns[name] = attack.cooldown

        self.targets_hit.clear()

        self.attack_box = pygame.FRect((0, 0), attack.size)
        self._update_hitbox_position(facing_right)
        return True

    def update(self, delta_time: float, facing_right: bool) -> None:
        if self.hurt_timer > 0:
            self.hurt_timer -= delta_time
            if self.hurt_timer <= 0:
                self.is_hurt = False

        for atk_name in self.cooldowns:
            if self.cooldowns[atk_name] > 0:
                self.cooldowns[atk_name] -= delta_time

        if self.current_attack:
            self.attack_timer -= delta_time
            if self.attack_timer <= 0:
                self.current_attack = None
                self.attack_box = None
                self.targets_hit.clear()
            else:
                self._update_hitbox_position(facing_right)

    def _update_hitbox_position(self, facing_right: bool) -> None:
        if not self.attack_box or not self.current_attack:
            return

        attack = self.attacks[self.current_attack]
        offset_x, offset_y = attack.offset

        if not facing_right:
            offset_x = -offset_x

        self.attack_box.center = (
            self.entity.hitbox.centerx + offset_x,
            self.entity.hitbox.centery + offset_y,
        )
