from typing import Optional
import pygame
import random

from src.states.state_machine import State


class EnemyHurtState(State):
    """Represent the EnemyHurt state."""
    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x = pygame.math.lerp(
                self.entity.velocity.x, 0.0, min(1.0, 3.0 * delta_time)
            )
        if not self.entity.combat.is_hurt:
            return "idle"
        return None


class EnemyIdleState(State):
    """Represent the EnemyIdle state."""
    def enter(self, previous: Optional[str] = None) -> None:
        """Enter the state."""
        self.entity.velocity.x = 0.0
        self.entity.patrol_timer = 0.0

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        if self.entity.can_see_player():
            return "chase"
        self.entity.patrol_timer += delta_time
        if self.entity.patrol_timer >= 0.5:
            return "patrol"
        return None


class EnemyPatrolState(State):
    """Represent the EnemyPatrol state."""
    def enter(self, previous: Optional[str] = None) -> None:

        """Enter the state."""
        self.entity.patrol_direction = 1 if random.random() > 0.5 else -1
        self.entity.patrol_timer = 0.0

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        if self.entity.can_see_player():
            return "chase"

        self.entity.facing_right = self.entity.patrol_direction > 0
        self.entity.velocity.x = (
            self.entity.patrol_direction * self.entity.chase_speed * 0.5
        )

        self.entity.patrol_timer += delta_time
        if self.entity.patrol_timer >= self.entity.patrol_interval:
            self.entity.patrol_direction *= -1
            self.entity.patrol_timer = 0.0

        if (self.entity.patrol_direction > 0 and self.entity.on_surface["right"]) or (
            self.entity.patrol_direction < 0 and self.entity.on_surface["left"]
        ):
            self.entity.patrol_direction *= -1
            self.entity.patrol_timer = 0.0

        return None


class EnemyChaseState(State):
    """Represent the EnemyChase state."""
    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        if self.entity.player is not None:
            self.entity.facing_right = (
                self.entity.player.hitbox.centerx > self.entity.hitbox.centerx
            )
            direction = 1.0 if self.entity.facing_right else -1.0
            self.entity.velocity.x = direction * self.entity.chase_speed
        if self.entity.is_player_in_range():
            return "attack"
        if not self.entity.can_see_player():
            return "idle"
        return None


class EnemyAttackState(State):
    """Represent the EnemyAttack state."""
    def __init__(self, entity):
        """Initialize the EnemyAttackState instance."""
        super().__init__(entity)
        self.attack_retry_timer = 0.0

    def enter(self, previous: Optional[str] = None) -> None:
        """Enter the state."""
        self.entity.velocity.x = 0.0
        success = self.entity.combat.start_attack(
            "claw_swipe", self.entity.facing_right
        )
        if not success:
            self.attack_retry_timer = 0.3
        else:
            self.attack_retry_timer = 0.0

    def update(self, delta_time: float) -> Optional[str]:

        """Update the current state."""
        if self.attack_retry_timer > 0:
            self.attack_retry_timer -= delta_time
            if self.attack_retry_timer <= 0:

                if not self.entity.combat.is_attacking:
                    return "chase" if self.entity.can_see_player() else "idle"

        if not self.entity.combat.is_attacking:
            return "chase" if self.entity.can_see_player() else "idle"
        return None


class EnemyStaggerState(State):
    """Represent the EnemyStagger state."""
    def enter(self, previous: Optional[str] = None) -> None:
        """Enter the state."""
        pass

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        if self.entity.stagger_timer <= 0:
            if self.entity.can_see_player():
                return "chase"
            else:
                return "idle"
        return None