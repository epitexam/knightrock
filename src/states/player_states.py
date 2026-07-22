from typing import Optional, Any

from src.states.state_machine import State
from src.core.settings import Combat as CombatSettings
from src.physics import apply_velocity_friction, lerp_velocity


class PlayerBaseState(State):
    """Represent the PlayerBase state."""

    def __init__(self, entity: Any, tags: Optional[list[str]] = None):
        """Initialize the PlayerBaseState instance."""
        super().__init__(entity, tags)

    def ground_return(self) -> str:
        """Determine the next state when returning to the ground."""
        if self.entity.on_surface["floor"]:
            return (
                "run" if (
                    self.entity.left_held or self.entity.right_held) else "idle"
            )
        return "fall"


class PlayerIdleState(PlayerBaseState):
    """Represent the PlayerIdle state."""

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state."""
        self.entity.velocity.x = 0

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        if not self.entity.on_surface["floor"]:
            return "fall"
        if self.entity.left_held or self.entity.right_held:
            return "run"
        return None


class PlayerRunState(PlayerBaseState):
    """Represent the PlayerRun state."""

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        self.entity.apply_horizontal_movement(delta_time)
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        if not self.entity.on_surface["floor"]:
            return "fall"
        if (
            not (self.entity.left_held or self.entity.right_held)
            and abs(self.entity.velocity.x) < 0.1
        ):
            return "idle"
        return None


class PlayerJumpState(PlayerBaseState):
    """Represent the PlayerJump state."""

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)
        if self.entity.velocity.y >= 0:
            return "fall"
        if self.entity._is_wall_sliding():
            return "wall_slide"
        return None


class PlayerFallState(PlayerBaseState):
    """Represent the PlayerFall state."""

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)
        if self.entity.velocity.y < 0:
            return "jump"
        if self.entity._is_wall_sliding():
            return "wall_slide"
        return self.ground_return()


class PlayerWallSlideState(PlayerBaseState):
    """Represent the PlayerWallSlide state."""

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state."""
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        self.entity.apply_horizontal_movement(delta_time)
        if self.entity.on_surface["floor"]:
            return "idle"
        if not self.entity._is_wall_sliding():
            return "fall"
        return None


class PlayerChargeState(PlayerBaseState):
    """Represent the PlayerCharge state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerChargeState instance with charge tags."""
        super().__init__(entity, tags=["charge", "busy"])

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, allowing limited movement while charging."""
        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity.combat.charging.is_charging:
            if self.entity.combat.is_attacking:
                return "attack"
            return self.ground_return()
        return None


class PlayerAttackState(PlayerBaseState):
    """Represent the PlayerAttack state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerAttackState instance with attack tags."""
        super().__init__(entity, tags=["attack", "busy"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state and apply forward momentum if grounded."""
        if self.entity.on_surface["floor"]:
            attack = self.entity.combat.state.current_attack_def
            multiplier = attack.lunge_speed_multiplier if attack else 0.35
            direction = 1.0 if self.entity.facing_right else -1.0
            self.entity.velocity.x = direction * self.entity.speed * multiplier

    def exit(self, next_state: Optional[str] = None) -> None:
        """Exit the state and cancel the ongoing attack."""
        self.entity.combat.state.end()

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state and check for buffered combo inputs."""
        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity.combat.is_attacking:
            if self.entity.state_machine.consume_input("attack"):
                return "attack"

            return self.ground_return()
        return None


class PlayerBlockState(PlayerBaseState):
    """Represent the PlayerBlock state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerBlockState instance with block tags."""
        super().__init__(entity, tags=["block", "busy"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state, stop horizontal velocity, and reduce hitbox height."""
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x = 0
        old_bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height -= CombatSettings.BLOCK_HEIGHT_REDUCTION
        self.entity.hitbox.bottom = old_bottom
        self.entity.sync_rects()

    def exit(self, next_state: Optional[str] = None) -> None:
        """Exit the state, restore hitbox height, and apply block cooldown."""
        if self.entity.block_stamina <= 0:
            self.entity.block_cooldown_timer = CombatSettings.BLOCK_COOLDOWN_BROKEN
        else:
            self.entity.block_cooldown_timer = CombatSettings.BLOCK_COOLDOWN_NORMAL
        old_bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height += CombatSettings.BLOCK_HEIGHT_REDUCTION
        self.entity.hitbox.bottom = old_bottom
        self.entity.handle_collisions("vertical")
        self.entity.sync_rects()

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, draining stamina and checking conditions."""
        self.entity.velocity.x = 0.0
        self.entity.block_stamina -= (
            delta_time if self.entity.on_surface["floor"] else delta_time * 2.0
        )
        if self.entity.block_stamina < 0:
            self.entity.block_stamina = 0.0
        if not self.entity.block_held or self.entity.block_stamina <= 0:
            return self.ground_return()
        return None


class PlayerHurtState(PlayerBaseState):
    """Represent the PlayerHurt state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerHurtState instance with invincibility tags."""
        super().__init__(entity, tags=["hurt", "invincible"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state and apply light knockback if provided."""
        self.entity._dash_requested = False

        knockback_dir = kwargs.get("knockback_direction", 0)
        knockback_force = kwargs.get("knockback_force", 0)
        if knockback_dir != 0 and knockback_force > 0:
            self.entity.velocity.x = knockback_dir * knockback_force

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, applying friction until hurt duration ends."""
        lerp_velocity(self.entity, 0.0, min(1.0, 5.0 * delta_time), delta_time)
        if not self.entity.combat.is_hurt:
            if self.entity.stagger_timer > 0:
                return "stagger"
            return self.ground_return()
        return None


class PlayerKnockbackState(PlayerBaseState):
    """Represent the PlayerKnockback state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerKnockbackState instance with knockback tags."""
        super().__init__(entity, tags=["knockback", "invincible"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state and apply strong launch velocity."""
        self.entity._dash_requested = False

        knockback_dir = kwargs.get("knockback_direction", 0)
        knockback_force = kwargs.get("knockback_force", 0)
        knockback_up = kwargs.get("knockback_up_force", 0)

        if knockback_dir != 0 and knockback_force > 0:
            self.entity.velocity.x = knockback_dir * knockback_force
        if knockback_up > 0:
            self.entity.velocity.y = -knockback_up

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, applying gravity and friction until landing."""
        if self.entity.on_surface["floor"]:
            lerp_velocity(self.entity, 0.0, min(
                1.0, 8.0 * delta_time), delta_time)
            if abs(self.entity.velocity.x) < 20.0 and abs(self.entity.velocity.y) < 1.0:
                self.entity.velocity.x = 0.0
                if self.entity.combat.is_hurt:
                    return "hurt"
                return self.ground_return()
        return None


class PlayerDashState(PlayerBaseState):
    """Represent the PlayerDash state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerDashState instance with dashing tags."""
        super().__init__(entity, tags=["dash", "invincible"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state, consume dash charge, and squish hitbox."""
        self.entity.dash_charges -= 1
        self.entity._dash_requested = False
        if self.entity.dash_charges == 0:
            self.entity.dash_penalty_timer = self.entity.dash_penalty_duration
        self.entity._original_hitbox_width = self.entity.hitbox.width
        new_width = self.entity._original_hitbox_width * 0.6
        self.entity.hitbox.x += (self.entity._original_hitbox_width -
                                 new_width) / 2
        self.entity.hitbox.width = new_width
        direction = 1 if self.entity.facing_right else -1
        self.entity.velocity.x = self.entity.dash_speed * direction
        self.entity.velocity.y = 0.0
        self.entity._dash_duration_timer = self.entity.dash_duration

    def exit(self, next_state: Optional[str] = None) -> None:
        """Exit the state and restore the original hitbox width."""
        current = self.entity.hitbox.width
        if current != self.entity._original_hitbox_width:
            self.entity.hitbox.x -= (
                self.entity._original_hitbox_width - current
            ) / 2
            self.entity.hitbox.width = self.entity._original_hitbox_width
            self.entity.handle_collisions("horizontal")
            self.entity.sync_rects()

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, applying dash friction and air control."""
        self.entity._dash_duration_timer -= delta_time
        friction = max(0.0, 1.0 - self.entity.dash_friction * delta_time)
        apply_velocity_friction(self.entity, friction, delta_time)
        if self.entity.left_held:
            self.entity.velocity.x -= 100.0 * delta_time
        if self.entity.right_held:
            self.entity.velocity.x += 100.0 * delta_time
        self.entity.velocity.y = 0.0
        if self.entity._dash_duration_timer <= 0 or abs(self.entity.velocity.x) < 10.0:
            self.entity.velocity.x = 0.0
            return self.ground_return()
        return None


class PlayerStaggerState(PlayerBaseState):
    """Represent the PlayerStagger state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerStaggerState instance with stagger tags."""
        super().__init__(entity, tags=["stagger", "busy"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state."""
        pass

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, applying friction until stagger ends."""
        if self.entity.on_surface["floor"]:
            lerp_velocity(self.entity, 0.0, min(
                1.0, 8.0 * delta_time), delta_time)

        if self.entity.stagger_timer <= 0:
            return self.ground_return()
        return None
