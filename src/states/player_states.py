from typing import Optional, Any

from src.states.state_machine import State
from src.core.settings import Combat as CombatSettings, Physics
from src.physics import apply_velocity_friction
from src.states.reaction_states import HurtState, KnockbackState, StaggerState


def player_ground_return(entity: Any) -> str:
    """Return the landing state name for the player.

    Shared by every reaction state so the landing decision lives in one
    place (archived duplication from ARCH-05).
    """
    if entity.on_surface["floor"]:
        return (
            "run" if (entity.left_held or entity.right_held) else "idle"
        )
    return "fall"


class PlayerBaseState(State):
    """Represent the PlayerBase state."""

    def __init__(self, entity: Any, tags: Optional[list[str]] = None):
        """Initialize the PlayerBaseState instance."""
        super().__init__(entity, tags)

    def ground_return(self) -> str:
        """Determine the next state when returning to the ground."""
        return player_ground_return(self.entity)


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
        if self.entity.is_wall_sliding():
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
        if self.entity.is_wall_sliding():
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
        if not self.entity.is_wall_sliding():
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
        """Cancel the attack unless this state is restarting a buffered one."""
        if next_state != "attack":
            self.entity.combat.state.end()

    def update(self, delta_time: float) -> str | tuple[str, dict[str, Any]] | None:
        """Update the current state and check for buffered combo inputs."""
        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity.combat.is_attacking:
            if self.entity.state_machine.consume_input("attack"):
                attack_name = self.entity._buffered_attack_name
                self.entity._buffered_attack_name = None
                if attack_name and self.entity.combat.start_attack(attack_name):
                    return ("attack", {"force": True})

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
        self.entity.block.apply_exit_cooldown()
        old_bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height += CombatSettings.BLOCK_HEIGHT_REDUCTION
        self.entity.hitbox.bottom = old_bottom
        self.entity.handle_collisions("vertical")
        self.entity.sync_rects()

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, draining stamina and checking conditions."""
        self.entity.velocity.x = 0.0
        drain = delta_time
        if not self.entity.on_surface["floor"]:
            drain = delta_time * CombatSettings.BLOCK_AIR_DRAIN_MULT
        self.entity.block.consume(drain)
        if not self.entity.block_held or self.entity.block.block_stamina <= 0:
            return self.ground_return()
        return None


class PlayerHurtState(HurtState):
    """Player hurt reaction: light knockback, then recover on the ground."""

    def __init__(self, entity: Any):
        super().__init__(
            entity,
            exit_resolver=self._hurt_exit,
            friction=Physics.HURT_FRICTION,
            tags=["hurt", "invincible"],
            on_enter=self._hurt_enter,
        )

    def _hurt_enter(self, **kwargs: Any) -> None:
        """Clear the dash request and apply the light knockback impulse."""
        self.entity.dash.cancel_request()

        knockback_dir = kwargs.get("knockback_direction", 0)
        knockback_force = kwargs.get("knockback_force", 0)
        if knockback_dir != 0 and knockback_force > 0:
            self.entity.velocity.x = knockback_dir * knockback_force

    def _hurt_exit(self) -> Optional[str]:
        """Transition to stagger if pending, otherwise to the ground state."""
        if self.entity.stagger_timer > 0:
            return "stagger"
        return player_ground_return(self.entity)


class PlayerKnockbackState(KnockbackState):
    """Player knockback reaction: strong launch, then ground recovery."""

    def __init__(self, entity: Any):
        super().__init__(
            entity,
            exit_resolver=self._knockback_exit,
            tags=["knockback", "invincible"],
            on_enter=self._knockback_enter,
        )

    def _knockback_enter(self, **kwargs: Any) -> None:
        """Clear the dash request before the launch velocity is applied."""
        self.entity.dash.cancel_request()

    def _knockback_exit(self) -> str:
        """Recover through hurt if still hurt, otherwise to the ground state."""
        if self.entity.combat.is_hurt:
            return "hurt"
        return player_ground_return(self.entity)


class PlayerDashState(PlayerBaseState):
    """Represent the PlayerDash state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerDashState instance with dashing tags."""
        super().__init__(entity, tags=["dash", "invincible"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state, consume dash charge, and squish hitbox."""
        self.entity.dash.consume_charge()
        self.entity.dash.apply_squish(self.entity.hitbox)
        direction = 1 if self.entity.facing_right else -1
        self.entity.velocity.x = self.entity.dash.speed * direction
        self.entity.velocity.y = 0.0
        self.entity.dash.duration_timer = self.entity.dash.duration

    def exit(self, next_state: Optional[str] = None) -> None:
        """Exit the state and restore the original hitbox width."""
        if self.entity.dash.restore_hitbox(self.entity.hitbox):
            self.entity.handle_collisions("horizontal")
            self.entity.sync_rects()

    def update(self, delta_time: float) -> Optional[str]:
        """Update the current state, applying dash friction and air control."""
        self.entity.dash.duration_timer -= delta_time
        friction = max(0.0, 1.0 - self.entity.dash.friction * delta_time)
        apply_velocity_friction(self.entity, friction, delta_time)
        if self.entity.left_held:
            self.entity.velocity.x -= Physics.DASH_AIR_CONTROL * delta_time
        if self.entity.right_held:
            self.entity.velocity.x += Physics.DASH_AIR_CONTROL * delta_time
        self.entity.velocity.y += (
            self.entity.normal_gravity
            * self.entity.dash.gravity_mult
            * delta_time
        )
        if (
            self.entity.dash.duration_timer <= 0
            or abs(self.entity.velocity.x) < 10.0
        ):
            self.entity.velocity.x = 0.0
            return self.ground_return()
        return None


class PlayerStaggerState(StaggerState):
    """Represent the PlayerStagger state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerStaggerState instance with stagger tags."""
        super().__init__(
            entity,
            exit_resolver=lambda: player_ground_return(self.entity),
            friction=Physics.STAGGER_FRICTION,
            tags=["stagger", "busy"],
        )
