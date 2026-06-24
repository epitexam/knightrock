from typing import Optional

import pygame

from src.states.state_machine import State


class EnemyHurtState(State):
    def update(self, delta_time: float) -> Optional[str]:
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x = pygame.math.lerp(
                self.entity.velocity.x, 0.0, min(1.0, 10.0 * delta_time)
            )
        if not self.entity.combat.is_hurt:
            return "patrol"
        return None


class EnemyPatrolState(State):
    def enter(self, previous: Optional[str] = None) -> None:
        self.entity.velocity.x = 0.0

    def update(self, delta_time: float) -> Optional[str]:
        if self.entity.can_see_player():
            return "chase"
        return None


class EnemyChaseState(State):
    def update(self, delta_time: float) -> Optional[str]:
        if self.entity.player is not None:
            self.entity.facing_right = (
                self.entity.player.hitbox.centerx > self.entity.hitbox.centerx
            )
            direction = 1.0 if self.entity.facing_right else -1.0
            self.entity.velocity.x = direction * self.entity.chase_speed

        if self.entity.is_player_in_range():
            return "attack"
        if not self.entity.can_see_player():
            return "patrol"
        return None


class EnemyAttackState(State):
    def enter(self, previous: Optional[str] = None) -> None:
        self.entity.velocity.x = 0.0
        self.entity.combat.start_attack("claw_swipe", self.entity.facing_right)

    def update(self, delta_time: float) -> Optional[str]:
        if not self.entity.combat.is_attacking:
            return "chase" if self.entity.can_see_player() else "patrol"
        return None
