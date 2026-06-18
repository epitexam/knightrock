from dataclasses import dataclass
from typing import Dict

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
    Manages attack hitboxes, animation states, and cooldowns.
    """

    def __init__(self, entity) -> None:
        self.entity = entity
        self.attacks: Dict[str, AttackData] = {}
        self.cooldowns: Dict[str, float] = {}

        self.current_attack: str | None = None
        self.attack_timer: float = 0.0
        self.attack_box: pygame.FRect | None = None

    def add_attack(self, name: str, data: AttackData) -> None:
        """Ajoute une attaque au répertoire de l'entité."""
        self.attacks[name] = data
        self.cooldowns[name] = 0.0

    @property
    def is_attacking(self) -> bool:
        return self.current_attack is not None

    def start_attack(self, name: str, facing_right: bool) -> bool:
        """
        Attempts to launch an attack.
        Returns True if the attack succeeded, False if it is on cooldown or if the entity is already attacking.
        """
        if self.is_attacking:
            return False
        if name not in self.attacks:
            return False
        if self.cooldowns[name] > 0:
            return False

        attack = self.attacks[name]
        self.current_attack = name
        self.attack_timer = attack.duration
        self.cooldowns[name] = attack.cooldown

        self.attack_box = pygame.FRect((0, 0), attack.size)
        self._update_hitbox_position(facing_right)
        return True

    def update(self, delta_time: float, facing_right: bool) -> None:
        """Updates timers, cooldowns, and the position of the offensive hitbox."""
        for atk_name in self.cooldowns:
            if self.cooldowns[atk_name] > 0:
                self.cooldowns[atk_name] -= delta_time

        if self.current_attack:
            self.attack_timer -= delta_time
            if self.attack_timer <= 0:
                self.current_attack = None
                self.attack_box = None
            else:
                self._update_hitbox_position(facing_right)

    def _update_hitbox_position(self, facing_right: bool) -> None:
        """Dynamically aligns the attack_box with the parent entity."""
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
