from typing import TYPE_CHECKING

import pygame

from state_machine import State

if TYPE_CHECKING:
    from player import Player


class PlayerState(State["Player"]):
    """
    Base class for all player states.
    Centralizes priority transitions: hurt, dash, block, attack.
    Provides helper for ground-state transitions.
    """

    def check_priority_transitions(self) -> str | None:
        """Checks high-priority transitions common to all states."""
        if self.entity.combat.is_hurt:
            return "hurt"

        if (
            self.entity._dash_requested
            and self.entity.dash_charges > 0
            and self.entity.state_machine is not None
            and self.entity.state_machine.current_state_name != "dash"
        ):
            return "dash"

        if (
            self.entity.on_surface["floor"]
            and self.entity.block_held
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

    def check_priority_transitions(self) -> str | None:
        """Only allow hurt and dash during wall slide (no block, no attack)."""
        if self.entity.combat.is_hurt:
            return "hurt"

        if (
            self.entity._dash_requested
            and self.entity.dash_charges > 0
            and self.entity.state_machine is not None
            and self.entity.state_machine.current_state_name != "dash"
        ):
            return "dash"

        return None

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

        old_bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height -= 16.0
        self.entity.hitbox.bottom = old_bottom
        self.entity.sync_rects()

    def exit(self) -> None:
        if self.entity.block_stamina <= 0:
            self.entity.block_cooldown_timer = 2.0
        else:
            self.entity.block_cooldown_timer = 0.5

        old_bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height += 16.0
        self.entity.hitbox.bottom = old_bottom
        self.entity.sync_rects()

    def update(self, delta_time: float) -> str | None:
        self.entity.velocity.x = 0.0

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


class PlayerDashState(PlayerState):
    """Smooth platformer dash with deceleration and light control."""

    def enter(self) -> None:
        self.entity.dash_charges -= 1
        self.entity._dash_requested = False

        if self.entity.dash_charges == 0:
            self.entity.dash_penalty_timer = self.entity.dash_penalty_duration

        self.entity._original_hitbox_width = self.entity.hitbox.width
        new_width = self.entity._original_hitbox_width * 0.6
        self.entity.hitbox.x += (self.entity._original_hitbox_width - new_width) / 2
        self.entity.hitbox.width = new_width

        direction = 1 if self.entity.facing_right else -1
        self.entity.velocity.x = self.entity.dash_speed * direction
        self.entity.velocity.y = 0.0

        self.entity._dash_duration_timer = self.entity.dash_duration

    def exit(self) -> None:
        """Restores the hitbox to its original size."""
        if hasattr(self.entity, "_original_hitbox_width"):
            current_width = self.entity.hitbox.width
            if current_width != self.entity._original_hitbox_width:
                self.entity.hitbox.x -= (
                    self.entity._original_hitbox_width - current_width
                ) / 2
                self.entity.hitbox.width = self.entity._original_hitbox_width

    def update(self, delta_time: float) -> str | None:
        self.entity._dash_duration_timer -= delta_time

        friction_factor = 1.0 - (self.entity.dash_friction * delta_time)
        if friction_factor < 0:
            friction_factor = 0.0
        self.entity.velocity.x *= friction_factor

        if self.entity.left_held:
            self.entity.velocity.x -= 100.0 * delta_time
        if self.entity.right_held:
            self.entity.velocity.x += 100.0 * delta_time

        self.entity.velocity.y = 0.0

        if self.entity._dash_duration_timer <= 0 or abs(self.entity.velocity.x) < 10.0:
            self.entity.velocity.x = 0.0
            return self.get_ground_return_state()

        return None
