from typing import TYPE_CHECKING

import pygame

from state_machine import State

if TYPE_CHECKING:
    from player import Player


class PlayerState(State["Player"]):
    """
    Base class for all player states.
    Centralizes priority transitions: hurt, block, attack.
    Provides helper for ground-state transitions.
    """

    def check_priority_transitions(self) -> str | None:
        """Checks high-priority transitions common to all states."""
        if self.entity.combat.is_hurt:
            return "hurt"

        if (
            self.entity.block_held
            and self.entity.block_cooldown_timer <= 0
            and self.entity.block_stamina > 0.3
        ):
            return "block"

        if self.entity.combat.is_attacking:
            return "attack"

        return None

    def get_ground_return_state(self) -> str:
        """
        Returns the appropriate state when the player is on ground:
        'run' if moving, 'idle' otherwise; 'fall' if airborne.
        """
        if self.entity.on_surface["floor"]:
            return (
                "run" if (self.entity.left_held or self.entity.right_held) else "idle"
            )
        return "fall"


class PlayerGroundedState(PlayerState):
    """
    Parent class for grounded states (Idle, Run).
    Adds jump and fall transitions on top of priority checks.
    """

    def check_global_transitions(self) -> str | None:
        """Checks priority transitions then jump and fall."""
        priority = self.check_priority_transitions()
        if priority:
            return priority

        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"

        if not self.entity.on_surface["floor"]:
            return "fall"

        return None


class PlayerHurtState(PlayerState):
    """Hit state (forced immobilization and knockback)."""

    def update(self, delta_time: float) -> str | None:

        control: float = (
            self.entity.floor_control
            if self.entity.on_surface["floor"]
            else self.entity.air_control
        )
        self.entity.velocity.x = pygame.math.lerp(
            self.entity.velocity.x, 0.0, min(1.0, control * delta_time)
        )

        if not self.entity.combat.is_hurt:
            return self.get_ground_return_state()

        return None


class PlayerIdleState(PlayerGroundedState):
    def enter(self) -> None:
        self.entity.velocity.x = 0

    def update(self, delta_time: float) -> str | None:
        transition = self.check_global_transitions()
        if transition:
            return transition

        if self.entity.left_held or self.entity.right_held:
            return "run"

        return None


class PlayerRunState(PlayerGroundedState):
    def update(self, delta_time: float) -> str | None:
        transition = self.check_global_transitions()
        if transition:
            return transition

        self.entity.apply_horizontal_movement(delta_time)

        is_moving = abs(self.entity.velocity.x) > 0.1
        input_active = self.entity.left_held or self.entity.right_held
        if not is_moving and not input_active:
            return "idle"

        return None


class PlayerJumpState(PlayerState):
    """State when the player gains altitude."""

    def update(self, delta_time: float) -> str | None:
        priority = self.check_priority_transitions()
        if priority:
            return priority

        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.velocity.y >= 0:
            return "fall"

        if self.entity._is_wall_sliding():
            return "wall_slide"

        return None


class PlayerFallState(PlayerState):
    """State when the player loses altitude."""

    def update(self, delta_time: float) -> str | None:
        priority = self.check_priority_transitions()
        if priority:
            return priority

        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.velocity.y < 0:
            return "jump"

        if self.entity._is_wall_sliding():
            return "wall_slide"

        return self.get_ground_return_state()


class PlayerWallSlideState(PlayerState):
    """State when the player slides against a wall."""

    def update(self, delta_time: float) -> str | None:
        priority = self.check_priority_transitions()
        if priority:
            return priority

        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"

        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity._is_wall_sliding():
            return "fall"

        if self.entity.on_surface["floor"]:
            return "idle"

        return None


class PlayerAttackState(PlayerState):
    def enter(self) -> None:
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x *= 0.1

    def update(self, delta_time: float) -> str | None:
        priority = self.check_priority_transitions()
        if priority:
            return priority

        if not self.entity.combat.is_attacking:
            return self.get_ground_return_state()

        return None


class PlayerBlockState(PlayerState):
    """State when the player is blocking (holding LSHIFT)."""

    def enter(self) -> None:
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x = 0

        self.entity.hitbox.height -= 16.0

        if self.entity.rect is not None:
            self.entity.hitbox.bottom = self.entity.rect.bottom

    def exit(self) -> None:
        if self.entity.block_stamina <= 0:
            self.entity.block_cooldown_timer = 2.0
        else:
            self.entity.block_cooldown_timer = 0.5

        self.entity.hitbox.height += 16.0

        if self.entity.rect is not None:
            self.entity.hitbox.bottom = self.entity.rect.bottom

    def update(self, delta_time: float) -> str | None:
        priority = self.check_priority_transitions()
        if priority:
            return priority

        if self.entity.on_surface["floor"]:
            self.entity.block_stamina -= delta_time
        else:
            self.entity.block_stamina -= delta_time * 2.0

        if not self.entity.block_held or self.entity.block_stamina <= 0:
            return self.get_ground_return_state()

        return None
