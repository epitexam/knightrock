from enum import Enum
from typing import Any

from src.combat.refusal import Refusal
from src.core.settings import Guard as GuardSettings
from src.core.settings import Locomotion, Physics, Turn
from src.physics import apply_velocity_friction
from src.states.reaction_states import HurtState, KnockbackState, StaggerState
from src.states.state_machine import State, StateMachine
from src.states.turn_state import TurnState


def _classify_ratio(ratio: float) -> str:
    """Classify from idle/reaction states using pure ratio thresholds."""
    if ratio >= Locomotion.WALK_PROMOTE:
        return PlayerState.RUN.value
    if ratio >= Locomotion.WALK_SLOW_PROMOTE:
        return PlayerState.WALK.value
    return PlayerState.WALK_SLOW.value


def resolve_locomotion_state(entity: Any, from_state: str | None = None) -> str:
    """Pick walk_slow/walk/run from |velocity.x| / entity.speed with hysteresis.

    ``from_state`` overrides the tier the hysteresis is measured against, and
    the pivot state needs it. The pivot absorbs the frames where the velocity
    sweeps through every tier on its way across zero, so resuming from it with
    the live state name would find no match, drop to :func:`_classify_ratio`,
    and flicker the tier boundaries exactly where they are being crossed at the
    fastest. The tier the pivot was entered from is the one the comparison has
    to continue from.
    """
    vx = abs(float(entity.velocity.x))
    base = float(getattr(entity, "speed", 0.0) or 0.0) or Physics.PLAYER_SPEED
    if base <= 0.0:
        return PlayerState.WALK_SLOW.value
    ratio = vx / base
    if from_state is None:
        from_state = str(
            getattr(getattr(entity, "state_machine", None), "current_state_name", "") or ""
        )
    if from_state in (PlayerState.RUN.value, PlayerState.RUN):
        if ratio < Locomotion.WALK_DEMOTE:
            return PlayerState.WALK.value
        return PlayerState.RUN.value
    if from_state in (PlayerState.WALK.value, PlayerState.WALK):
        if ratio >= Locomotion.WALK_PROMOTE:
            return PlayerState.RUN.value
        if ratio < Locomotion.WALK_SLOW_DEMOTE:
            return PlayerState.WALK_SLOW.value
        return PlayerState.WALK.value
    if from_state in (PlayerState.WALK_SLOW.value, PlayerState.WALK_SLOW):
        if ratio >= Locomotion.WALK_SLOW_PROMOTE:
            return PlayerState.WALK.value
        return PlayerState.WALK_SLOW.value
    return _classify_ratio(ratio)


def player_ground_return(entity: Any) -> str:
    """Return the landing state name for the player.

    Shared by every reaction state so the landing decision lives in one
    place (archived duplication from ARCH-05).
    """
    if entity.on_surface["floor"]:
        if entity.left_held or entity.right_held:
            return resolve_locomotion_state(entity)
        return "idle"
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
            return resolve_locomotion_state(self.entity)
        return None


class PlayerGroundLocomotionState(PlayerBaseState):
    """Shared update for walk_slow / walk / run on the ground."""

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
        return resolve_locomotion_state(self.entity)


class PlayerRunState(PlayerGroundLocomotionState):
    """Represent the PlayerRun state."""


class PlayerWalkState(PlayerGroundLocomotionState):
    """Mid-speed ground tier (analog input / combat movement multiplier)."""


class PlayerWalkSlowState(PlayerGroundLocomotionState):
    """Slow ground tier (Guard MOVE_MULT, partial analog stick)."""


class PlayerTurnState(TurnState):
    """The player's pivot: where to go, and how the player leaves the floor.

    All of the hold itself -- arming it, keeping the fighter moving, freezing
    the mirror, committing it on the way out -- is in :class:`TurnState`, which
    the enemy's pivot shares. Only the three answers below are the player's.

    The jump hook is not a nicety: the pivot calls
    ``apply_horizontal_movement`` every tick, and without the jump the player
    could not leave the ground from inside a hold at all. It reads as a fighter
    who is locked to the floor for the length of a pivot, which is a different
    bug with the same shape.
    """

    def resume_state(self) -> str:
        """Back to the locomotion tier the pivot interrupted.

        ``resume``, captured on entry, not the live state name. The hold spans
        the frames where the velocity sweeps through ``run``, ``walk`` and
        ``walk_slow`` on its way across zero, so resuming from ``turn`` would
        match none of the hysteresis branches and drop to a plain ratio
        classification -- flickering the tier boundaries, and with them the
        animation clock and the footstep cadence, at exactly the moment the
        fighter is moving fastest.
        """
        return resolve_locomotion_state(self.entity, self.resume)

    def _before_move(self, delta_time: float) -> str | None:
        """A jump leaves the hold for the air states."""
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        return None

    def _lost_the_ground(self) -> str:
        """Walked off an edge mid-pivot."""
        return "fall"


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
    """Hold-to-crouch: a low, shuffling ground posture that can still fight.

    The collider height is *not* owned here. It belongs to
    :class:`~src.entities.crouch_posture.CrouchPosture`, which the player ticks
    every frame, so the blend runs through this state, through an attack out of
    it, and through a guard out of it alike. A height owned by the state could
    only be eased while the state was active, which meant every interrupt --
    attacking, guarding, dashing -- snapped it back to full in one tick.

    Leaving is gated on the collider having finished standing back up, so a
    release under a low ceiling -- where the blend stops at the headroom and
    never arrives -- holds the posture instead of leaving it half-risen.

    Movement is a slow shuffle, not a stop: the fighter keeps whatever
    horizontal speed they carried in and accelerates from there under a
    ``CROUCH_SPEED_MULT`` axis. Zeroing the velocity on entry (the old
    behaviour) meant a fighter at full run lost every pixel of momentum the
    instant they pressed Down and had to re-accelerate from nothing on the way
    out. ``_crouch_return`` reads the held direction so the shuffle resumes into
    the right locomotion tier instead of dropping to idle.
    """

    def __init__(self, entity: Any):
        super().__init__(entity, tags=["crouch", "busy"])

    def update(self, delta_time: float) -> str | None:
        saved_axis = self.entity.move_axis
        self.entity.move_axis = saved_axis * Physics.CROUCH_SPEED_MULT
        self.entity.apply_horizontal_movement(delta_time)
        self.entity.move_axis = saved_axis
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        if not self.entity.on_surface["floor"]:
            return "fall"
        if not _wants_crouch(self.entity) and _is_fully_stood(self.entity):
            return self._crouch_return()
        return None

    def _crouch_return(self) -> str:
        """Ground return that resumes into locomotion when a direction is held."""
        if self.entity.left_held or self.entity.right_held:
            return resolve_locomotion_state(self.entity)
        return "idle"


class PlayerAttackState(PlayerBaseState):
    """Represent the PlayerAttack state."""

    def __init__(self, entity: Any):
        """Initialize the PlayerAttackState instance with attack tags."""
        super().__init__(entity, tags=["attack", "busy"])

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state and apply forward momentum if grounded.

        Off the ground the horizontal lunge is skipped -- a fighter who lunges
        on the ground overshoots the target -- and the vertical impulse takes its
        place. ``vertical_lunge`` is a multiple of ``jump_height``, signed so
        positive rises, matching the jump itself.

        The impulse is a *floor* on the fighter's momentum in the direction it
        pushes, never a replacement for it. Overwriting would mean that pressing
        the rising aerial a frame after a full jump replaces ``-jump_height``
        with ``-0.62 * jump_height``: the attack would make the fighter rise
        more slowly than the jump that put them in the air, which is the one
        thing a follow-up should never do. So a rise takes
        ``min(current, -lunge)`` and a dive ``max(current, +lunge)``. A fighter
        already going up faster than the move lifts keeps the arc they earned,
        and a fighter already falling faster than the dive drops keeps it.

        The horizontal momentum an airborne fighter keeps is not set here but
        read every frame from ``attack_move_multiplier``, so a move that wants
        to carry forward sets that instead and inherits whatever horizontal
        velocity the fighter arrived with.
        """
        attack = self.entity.combat.state.current_attack_def
        if self.entity.on_surface["floor"]:
            multiplier = attack.lunge_speed_multiplier if attack else 0.35
            direction = 1.0 if self.entity.facing_right else -1.0
            self.entity.velocity.x = direction * self.entity.speed * multiplier
        elif attack is not None and attack.vertical_lunge:
            impulse = -self.entity.jump_height * attack.vertical_lunge
            if impulse < 0.0:
                self.entity.velocity.y = min(self.entity.velocity.y, impulse)
            else:
                self.entity.velocity.y = max(self.entity.velocity.y, impulse)

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
                # Re-asked at *consumption*, not trusted from when it was
                # buffered. A press buffered during a sweep and consumed after
                # the fighter stood up has to be refused for the wrong posture,
                # which is what ``start_attack`` answers -- and what the old
                # code could not, since it cleared the name and fired whatever
                # it had stored.
                if attack_name and self.entity.combat.start_attack(attack_name) is Refusal.NONE:
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
        if self.entity.stagger_timer <= 0:
            return player_ground_return(self.entity)
        return None


class PlayerState(str, Enum):
    """Enumeration of player states for type safety and refactoring reliability."""

    IDLE = "idle"
    WALK_SLOW = "walk_slow"
    WALK = "walk"
    RUN = "run"
    TURN = Turn.STATE
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


def dash_cancel_open(player: Any) -> bool:
    """Whether a dash has run long enough to be cancelled (attack/guard).

    ``Physics.DASH_CANCEL_WINDOW`` is measured from the dash start, so the
    comparison uses the *remaining* timer (``duration - duration_timer``).
    Note the 60 Hz granularity: interrupts are evaluated before the dash state
    decrements its timer, so a press is accepted on the frame *after* the
    window is crossed. With the shipped ``0.0`` window every dash frame but the
    first accepts a cancel; any positive value is a deliberate commitment.

    Single source of truth for the cancel window: ``Player.may_attack_now`` and
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
    # ``CROUCH`` is deliberately absent: crouch-guard is a posture, not a
    # different move. It used to be refused outright, which both ate the press
    # (no buffer, unlike the attack path) and left the whole low/overhead half of
    # ``Guard.HEIGHT_BLOCK`` unreachable in play. ``Player.receive_damage``
    # reads the crouch flag off the state, so guarding from crouch resolves
    # those rows.
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

    ``Player.may_attack_now()`` is deliberately *not* a precondition, and
    ``start_attack`` is where the decision belongs now. This interrupt has a job
    the combat component cannot do: it has to know that an attack is *running*,
    because it replaces the ``ATTACK`` state. Without that test a press refused
    further down -- on cooldown, in the wrong posture -- would drop the fighter
    into an attack state with nothing running.

    The dash branch is here for the same reason it was once dead code: a dash
    has to be cancellable into an attack, which is a question about the *state*
    rather than about the move.

    The coyote bypass opens the cancel on frames where the dash has already
    ended. It is the one place this and ``Player.may_attack_now`` answer
    differently for the same fighter, and it is deliberate: a press just after a
    dash should still connect.
    """
    if not player.combat.is_attacking:
        return False
    current = player.state_machine.current_state_name
    # A dash has to be cancellable into an attack; the window is the commitment.
    if current == PlayerState.DASH:
        return dash_cancel_open(player)
    # The coyote window survives the dash for a few frames, and a press inside
    # it should still connect.
    if bool(player.dash.in_coyote()):
        return True
    # Everything else is ``start_attack``'s call: cooldowns, cancellations, the
    # fighter's posture and whether they are hurt. Only the transition itself is
    # answered here.
    return True


def _wants_crouch(player: Any) -> bool:
    down = bool(getattr(player, "down_held", False))
    grounded = bool(player.on_surface.get("floor", False))
    return down and grounded


def _is_fully_stood(player: Any) -> bool:
    """Whether the crouch blend has finished standing the fighter back up.

    Never true under a low ceiling, which is the point: the posture is left once
    there is room to leave it, not on the tick the button came up.
    """
    return bool(getattr(getattr(player, "crouch", None), "is_fully_stood", True))


def _can_crouch(player: Any) -> bool:
    """Whether the player may crouch from the state they are in.

    ``turn`` is in there because a pivot is locomotion with a lean on it, and a
    fighter who cannot crouch for the length of the hold has lost a move for
    two hundred milliseconds because they turned around. The states not listed
    are genuinely incompatible with it: they have already answered a different
    question about what the fighter is doing.
    """
    if not _wants_crouch(player):
        return False
    return player.state_machine.current_state_name in (
        PlayerState.IDLE,
        PlayerState.WALK_SLOW,
        PlayerState.WALK,
        PlayerState.RUN,
        PlayerState.TURN,
    )


def configure_player_state_machine(player: Any) -> None:
    """Build the 17-state player machine (moved from Player, audit F1.1)."""
    sm = StateMachine(player)
    player.state_machine = sm
    sm.add_state(PlayerState.IDLE, PlayerIdleState(player))
    sm.add_state(PlayerState.WALK_SLOW, PlayerWalkSlowState(player))
    sm.add_state(PlayerState.WALK, PlayerWalkState(player))
    sm.add_state(PlayerState.RUN, PlayerRunState(player))
    sm.add_state(PlayerState.TURN, PlayerTurnState(player))
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
