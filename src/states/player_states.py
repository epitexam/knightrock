from enum import Enum
from typing import Any

from src.core.settings import Guard as GuardSettings
from src.core.settings import Locomotion, Physics
from src.physics import apply_velocity_friction
from src.states.reaction_states import HurtState, KnockbackState, StaggerState
from src.states.state_machine import State, StateMachine


def player_ground_return(entity: Any) -> str:
    """Return the landing state name for the player.

    Shared by every reaction state so the landing decision lives in one
    place (archived duplication from ARCH-05).
    """
    if entity.on_surface["floor"]:
        return "run" if (entity.left_held or entity.right_held) else "idle"
    return "fall"


class PlayerBaseState(State):
    """Represent the PlayerBase state."""

    def __init__(self, entity: Any, tags: list[str] | None = None):
        """Initialize the PlayerBaseState instance."""
        super().__init__(entity, tags)

    def ground_return(self) -> str:
        """Determine the next state when returning to the ground."""
        return player_ground_return(self.entity)


class PlayerIdleState(PlayerBaseState):
    """Represent the PlayerIdle state."""

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state."""
        self.entity.velocity.x = 0

    def update(self, delta_time: float) -> str | None:
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

    def update(self, delta_time: float) -> str | None:
        """Update the current state."""
        self.entity.apply_horizontal_movement(delta_time)
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        if not self.entity.on_surface["floor"]:
            return "fall"
        if (
            not (self.entity.left_held or self.entity.right_held)
            and abs(self.entity.velocity.x) < Locomotion.RUN_STOP_SPEED_PX_S
        ):
            return "idle"
        return None


class PlayerJumpState(PlayerBaseState):
    """Represent the PlayerJump state."""

    def update(self, delta_time: float) -> str | None:
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

    def update(self, delta_time: float) -> str | None:
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

    def update(self, delta_time: float) -> str | None:
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

    def update(self, delta_time: float) -> str | None:
        """Update the current state, allowing limited movement while charging."""
        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity.combat.charging.is_charging:
            if self.entity.combat.is_attacking:
                return "attack"
            return self.ground_return()
        return None


class PlayerCrouchState(PlayerBaseState):
    def __init__(self, entity: Any):
        super().__init__(entity, tags=["crouch", "busy"])
        self._stood_height: float = 0.0

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        self.entity.velocity.x = 0
        self._stood_height = self.entity.hitbox.height
        bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height = self._stood_height * Physics.CROUCH_HEIGHT_FACTOR
        self.entity.hitbox.bottom = bottom
        self.entity.sync_rects()

    def update(self, delta_time: float) -> str | None:
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        if not self.entity.on_surface["floor"]:
            return "fall"
        if not _wants_crouch(self.entity):
            if self._can_stand():
                return self.ground_return()
            return None
        return None

    def exit(self, next_state: str | None = None) -> None:
        if self._stood_height <= 0:
            return
        bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height = self._stood_height
        self.entity.hitbox.bottom = bottom
        self.entity.handle_collisions("horizontal")
        self.entity.sync_rects()
        self._stood_height = 0.0

    def _can_stand(self) -> bool:
        if self._stood_height <= 0:
            return True
        probe = self.entity.hitbox.copy()
        probe.height = self._stood_height
        probe.bottom = self.entity.hitbox.bottom
        for sprite in self.entity.collision_sprites:
            box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
            if box is not None and probe.colliderect(box):
                return False
        return True


class PlayerAttackState(PlayerBaseState):
    """Represent the PlayerAttack state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerAttackState instance with attack tags."""
        super().__init__(entity, tags=["attack", "busy"])

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state and apply forward momentum if grounded."""
        if self.entity.on_surface["floor"]:
            attack = self.entity.combat.state.current_attack_def
            multiplier = attack.lunge_speed_multiplier if attack else 0.35
            direction = 1.0 if self.entity.facing_right else -1.0
            self.entity.velocity.x = direction * self.entity.speed * multiplier

    def exit(self, next_state: str | None = None) -> None:
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


class PlayerGuardState(PlayerBaseState):
    def __init__(self, entity: Any):
        super().__init__(entity, tags=["guard", "busy"])

    def update(self, delta_time: float) -> str | None:
        self.entity.handle_jump()
        saved_axis = self.entity.move_axis
        self.entity.move_axis = saved_axis * GuardSettings.MOVE_MULT
        self.entity.apply_horizontal_movement(delta_time)
        self.entity.move_axis = saved_axis
        if self.entity.guard.posture <= 0:
            return "stagger"
        if not self.entity.guard_held or not self.entity.guard.can_use():
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

    def _hurt_exit(self) -> str | None:
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

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state, consume dash charge, and squish hitbox."""
        self.entity.dash.consume_charge()
        self.entity.dash.apply_squish(self.entity.hitbox)
        # Dash direction follows captured request move_axis if set, otherwise current input (move_axis), otherwise facing
        request_axis = getattr(self.entity.dash, "request_move_axis", 0.0)
        move_axis = request_axis if request_axis != 0.0 else getattr(self.entity, "move_axis", 0.0)
        direction = (
            1.0
            if move_axis > 0
            else -1.0
            if move_axis < 0
            else (1.0 if self.entity.facing_right else -1.0)
        )
        self.entity.velocity.x = self.entity.dash.speed * direction
        self.entity.velocity.y = 0.0
        self.entity.dash.duration_timer = self.entity.dash.duration
        # Signal dash start for screen shake/trauma
        self.entity._dash_started_this_frame = True

    def exit(self, next_state: str | None = None) -> None:
        """Exit the state and restore the original hitbox width."""
        if self.entity.dash.restore_hitbox(self.entity.hitbox):
            self.entity.handle_collisions("horizontal")
            self.entity.sync_rects()
        # Start dash coyote window for attack/guard after dash ends
        self.entity.dash.start_coyote()

    def update(self, delta_time: float) -> str | None:
        """Update the current state, applying dash friction and air control."""
        self.entity.dash.duration_timer -= delta_time
        # Full directional control: input directly influences velocity for snappy changes
        move_axis = getattr(self.entity, "move_axis", 0.0)
        if move_axis != 0.0:
            target_vx = self.entity.dash.speed * move_axis
            # Strong acceleration toward target velocity for instant direction response (Brawlhalla-style)
            control_accel = Physics.DASH_AIR_CONTROL * delta_time
            diff = target_vx - self.entity.velocity.x
            # If trying to reverse direction, apply extra impulse for instant turn
            if diff * self.entity.velocity.x < 0:  # Opposite signs = reversing
                control_accel *= 5.0  # 5x stronger when reversing
            if abs(diff) > control_accel:
                self.entity.velocity.x += control_accel if diff > 0 else -control_accel
            else:
                self.entity.velocity.x = target_vx
            # No friction while actively controlling - player has full authority
        else:
            # No input: apply friction to slow down naturally
            friction = max(0.0, 1.0 - self.entity.dash.friction * delta_time)
            apply_velocity_friction(self.entity, friction, delta_time)

        # Wall bounce: if dashing into a wall, bounce off with momentum retention
        if self.entity.on_surface.get("left", False) and self.entity.velocity.x < 0:
            self.entity.velocity.x = -self.entity.velocity.x * Physics.DASH_WALL_BOUNCE
            self.entity.facing_right = True
        elif self.entity.on_surface.get("right", False) and self.entity.velocity.x > 0:
            self.entity.velocity.x = -self.entity.velocity.x * Physics.DASH_WALL_BOUNCE
            self.entity.facing_right = False

        self.entity.velocity.y += (
            self.entity.normal_gravity * self.entity.dash.gravity_mult * delta_time
        )
        if self.entity.dash.duration_timer <= 0 or abs(self.entity.velocity.x) < 10.0:
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


class PlayerDizzyState(State):
    """Represent the PlayerDizzy state from consecutive perfect parries received."""

    def __init__(self, entity: Any):
        super().__init__(entity, tags=["dizzy", "busy"])

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        duration = kwargs.get("duration", 0.0)
        if duration > 0:
            self.entity.stagger_timer = duration

    def update(self, delta_time: float) -> str | None:
        if self.entity.stagger_timer > 0:
            self.entity.stagger_timer -= delta_time
        if self.entity.stagger_timer <= 0:
            return player_ground_return(self.entity)
        return None


class PlayerState(str, Enum):
    """Enumeration of player states for type safety and refactoring reliability."""

    IDLE = "idle"
    RUN = "run"
    JUMP = "jump"
    FALL = "fall"
    WALL_SLIDE = "wall_slide"
    ATTACK = "attack"
    GUARD = "guard"
    HURT = "hurt"
    DASH = "dash"
    STAGGER = "stagger"
    CHARGE = "charge"
    CROUCH = "crouch"
    KNOCKBACK = "knockback"
    DIZZY = "dizzy"


ATTACK_FORBIDDEN_STATES = {
    PlayerState.WALL_SLIDE,
    PlayerState.GUARD,
    PlayerState.CROUCH,
    PlayerState.HURT,
    PlayerState.DASH,
    PlayerState.STAGGER,
    PlayerState.KNOCKBACK,
    PlayerState.DIZZY,
}
"""Set of states where initiating an attack is forbidden."""


def dash_cancel_open(player: Any) -> bool:
    """Whether a dash has run long enough to be cancelled (attack/guard).

    ``Physics.DASH_CANCEL_WINDOW`` is measured from the dash start, so the
    comparison uses the *remaining* timer (``duration - duration_timer``).
    Note the 60 Hz granularity: interrupts are evaluated before the dash state
    decrements its timer, so a press is accepted on the frame *after* the
    window is crossed. With the shipped ``0.0`` window every dash frame but the
    first accepts a cancel; any positive value is a deliberate commitment.

    Single source of truth for the cancel window: ``Player.can_attack`` and
    the state-machine interrupts (``_can_guard`` / ``_can_attack_interrupt``)
    all read it, so the input gate and the transition can never disagree.
    """
    dash = player.dash
    elapsed = dash.duration - dash.duration_timer
    return bool(elapsed >= Physics.DASH_CANCEL_WINDOW)


def _can_dash(player: Any) -> bool:
    """Check if the player can currently interrupt to dash."""
    return player.dash.can_use() and player.state_machine.current_state_name not in (
        PlayerState.DASH,
        PlayerState.HURT,
        PlayerState.KNOCKBACK,
        PlayerState.STAGGER,
    )


def _can_guard(player: Any) -> bool:
    if not (player.guard_held and player.guard.can_use()):
        return False
    current = player.state_machine.current_state_name
    if current == PlayerState.CROUCH:
        return False
    # Allow guard cancel from dash after cancel window
    if current == PlayerState.DASH:
        return dash_cancel_open(player)
    # Allow guard during dash coyote window
    if bool(player.dash.in_coyote()):
        return True
    return current not in (
        PlayerState.WALL_SLIDE,
        PlayerState.HURT,
        PlayerState.KNOCKBACK,
        PlayerState.DASH,
        PlayerState.STAGGER,
        PlayerState.ATTACK,
    )


def _can_attack_interrupt(player: Any) -> bool:
    """Check if the player can currently interrupt to attack.

    ``Player.can_attack()`` is deliberately *not* a precondition: it forbids
    ``DASH`` outright, which used to make the dash branch below unreachable
    (pressing an attack mid-dash was swallowed). The state test that follows
    already covers every forbidden state, so the dash window stays the only
    thing that gates a dash cancel.
    """
    if not player.combat.is_attacking:
        return False
    current = player.state_machine.current_state_name
    # Allow attack cancel from dash after cancel window
    if current == PlayerState.DASH:
        return dash_cancel_open(player)
    # Allow attack during dash coyote window
    if bool(player.dash.in_coyote()):
        return True
    return current not in ATTACK_FORBIDDEN_STATES


def _wants_crouch(player: Any) -> bool:
    down = bool(getattr(player, "down_held", False))
    grounded = bool(player.on_surface.get("floor", False))
    return down and grounded


def _can_crouch(player: Any) -> bool:
    if not _wants_crouch(player):
        return False
    return player.state_machine.current_state_name in (
        PlayerState.IDLE,
        PlayerState.RUN,
    )


def configure_player_state_machine(player: Any) -> None:
    """Build the 14-state player machine (moved from Player, audit F1.1)."""
    sm = StateMachine(player)
    player.state_machine = sm
    sm.add_state(PlayerState.IDLE, PlayerIdleState(player))
    sm.add_state(PlayerState.RUN, PlayerRunState(player))
    sm.add_state(PlayerState.JUMP, PlayerJumpState(player))
    sm.add_state(PlayerState.FALL, PlayerFallState(player))
    sm.add_state(PlayerState.WALL_SLIDE, PlayerWallSlideState(player))
    sm.add_state(PlayerState.ATTACK, PlayerAttackState(player))
    sm.add_state(PlayerState.CHARGE, PlayerChargeState(player))
    sm.add_state(PlayerState.CROUCH, PlayerCrouchState(player))
    sm.add_state(PlayerState.GUARD, PlayerGuardState(player))
    sm.add_state(PlayerState.HURT, PlayerHurtState(player))
    sm.add_state(PlayerState.KNOCKBACK, PlayerKnockbackState(player))
    sm.add_state(PlayerState.DASH, PlayerDashState(player))
    sm.add_state(PlayerState.STAGGER, PlayerStaggerState(player))
    sm.add_state(PlayerState.DIZZY, PlayerDizzyState(player))
    sm.set_initial_state(PlayerState.IDLE)
    sm.add_interrupt(PlayerState.DASH, lambda: _can_dash(player), priority=80)
    sm.add_interrupt(PlayerState.GUARD, lambda: _can_guard(player), priority=60)
    sm.add_interrupt(PlayerState.CROUCH, lambda: _can_crouch(player), priority=30)
    sm.add_interrupt(PlayerState.ATTACK, lambda: _can_attack_interrupt(player), priority=40)
