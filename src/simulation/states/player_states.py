from enum import Enum
from typing import TYPE_CHECKING, cast

from src.simulation.combat.frame_data import PhaseState
from src.simulation.physics import apply_velocity_friction
from src.simulation.settings import Locomotion, Physics
from src.simulation.states.reaction_states import (
    HurtState,
    KnockbackState,
    StaggerState,
    apply_reaction_drag,
)
from src.simulation.states.state_machine import State, StateMachine
from src.simulation.states.turn_state import TurnState

if TYPE_CHECKING:
    from src.simulation.entities.player import Player


def _classify_ratio(ratio: float) -> str:
    """Classify from idle/reaction states using pure ratio thresholds."""
    if ratio >= Locomotion.WALK_PROMOTE:
        return PlayerState.RUN.value
    if ratio >= Locomotion.WALK_SLOW_PROMOTE:
        return PlayerState.WALK.value
    return PlayerState.WALK_SLOW.value


def resolve_locomotion_state(entity: Player, from_state: str | None = None) -> str:
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
    base = float(entity.speed) or Physics.PLAYER_SPEED
    if base <= 0.0:
        return PlayerState.WALK_SLOW.value
    ratio = vx / base
    if from_state is None:
        from_state = str(entity.state_machine.current_state_name or "")
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


def player_ground_return(entity: Player) -> str:
    """Return the landing state name for the player.

    Shared by every reaction state so the landing decision lives in one
    place (archived duplication from ARCH-05).
    """
    if entity.on_surface["floor"]:
        if entity.left_held or entity.right_held:
            return resolve_locomotion_state(entity)
        return "idle"
    return "fall"


class PlayerBaseState(State["Player"]):
    """Represent the PlayerBase state."""

    def __init__(self, entity: Player, tags: list[str] | None = None):
        """Initialize the PlayerBaseState instance."""
        super().__init__(entity, tags)

    def ground_return(self) -> str:
        """Determine the next state when returning to the ground."""
        return player_ground_return(self.entity)


class PlayerIdleState(PlayerBaseState):
    """Represent the PlayerIdle state."""

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
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


class PlayerTurnState(TurnState["Player"]):
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
    snapshot_fields: tuple[str, ...] = ()

    """Represent the PlayerCharge state."""

    def __init__(self, entity: Player):
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

    def exit(self, next_state: str | None = None) -> None:
        """Drop the charge on the way out, unless an attack is taking it over.

        Leaving this state by any other route -- a dash, a hurt, a state the
        machine reached for -- left ``charging`` standing, and a standing charge
        keeps growing, keeps multiplying the movement, and makes
        ``start_attack`` refuse the release: the heavy was unreachable until
        something hit the fighter.
        """
        if next_state == "attack":
            return
        self.entity.combat.charging.cancel()


class PlayerAttackState(PlayerBaseState):
    snapshot_fields = ("_started",)

    """Represent the PlayerAttack state."""

    def __init__(self, entity: Player):
        """Initialize the PlayerAttackState instance with attack tags."""
        super().__init__(entity, tags=["attack", "busy"])
        self._started = 0

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        """Start the move's momentum, and remember which attack it was."""
        self._started = self.entity.combat.attacks_started
        self._lunge()

    def _lunge(self) -> None:
        """Apply the running move's momentum: forward on the ground, vertical in the air.

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
            impulse = -self.entity.jump.jump_height * attack.vertical_lunge
            if impulse < 0.0:
                self.entity.velocity.y = min(self.entity.velocity.y, impulse)
            else:
                self.entity.velocity.y = max(self.entity.velocity.y, impulse)

    def exit(self, next_state: str | None = None) -> None:
        """Cancel the attack unless this state is restarting a buffered one."""
        if next_state != "attack":
            self.entity.combat.state.end()

    def update(self, delta_time: float) -> str | tuple[str, dict[str, object]] | None:
        """Move, give each new link of a chain its own lunge, and leave when done.

        A chain link starts while this state is running -- the input handler
        cancels one move into the next -- so the state is not re-entered and
        would not lunge again; the attack counter is how it sees the new move.
        A press for after the attack is the input handler's buffer, not this
        state's.
        """
        if self._jump_cancel():
            return "jump"
        started = self.entity.combat.attacks_started
        if started != self._started:
            self._started = started
            self._lunge()
        self.entity.apply_horizontal_movement(delta_time)
        if not self.entity.combat.is_attacking:
            return self.ground_return()
        return None

    def _jump_cancel(self) -> bool:
        """Jump out of an attack that has hit, to follow a launched target up.

        Only once the running phase has touched someone: a whiff stays
        committed. The jump is the ordinary one -- from the ground, off a
        wall or in the air while a midair jump is left -- so the press is
        spent only if a jump actually happened.
        """
        player = self.entity
        state = player.combat.state
        if not (player.jump.has_buffered_jump() and state.targets_hit):
            return False
        if state.sub_state not in (PhaseState.ACTIVE, PhaseState.RECOVERY):
            return False
        player.handle_jump()
        return player.jump.jump_buffer_timer <= 0.0


class PlayerGuardState(PlayerBaseState):
    """The guard, held: every blow from the front is stopped, but the guard is
    slow to move in and a punch, a kick or a charged blow breaks it."""

    def __init__(self, entity: Player):
        super().__init__(entity, tags=["guard", "busy"])

    def update(self, delta_time: float) -> str | None:
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        saved_axis = self.entity.move_axis
        self.entity.move_axis = saved_axis * GUARD_MOVE_MULT
        self.entity.apply_horizontal_movement(delta_time)
        self.entity.move_axis = saved_axis
        if not _wants_guard(self.entity) or _wants_recharge(self.entity):
            return self.ground_return()
        return None


class PlayerRechargeState(PlayerBaseState):
    """Guard and Down held on the ground: the blade's battery fills, and the
    fighter stands there, open."""

    def __init__(self, entity: Player):
        super().__init__(entity, tags=["recharge", "busy"])

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        self.entity.velocity.x = 0.0

    def update(self, delta_time: float) -> str | None:
        apply_velocity_friction(self.entity, Physics.FLOOR_CONTROL, delta_time)
        self.entity.battery.recharge(delta_time)
        if not _wants_recharge(self.entity):
            return self.ground_return()
        return None


class PlayerPromptState(PlayerBaseState):
    """A prompt is up -- death blow, throw, blade lock: the fighter stands still
    and untouchable until it is answered."""

    def __init__(self, entity: Player):
        super().__init__(entity, tags=["prompt", "busy", "invincible"])

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        self.entity.velocity.x = 0.0

    def update(self, delta_time: float) -> str | None:
        self.entity.velocity.x = 0.0
        if self.entity.prompt.active:
            return None
        if self.entity.combat.is_attacking:
            return "attack"
        return self.ground_return()


class PlayerHurtState(HurtState["Player"]):
    """Player hurt reaction: light knockback, then recover on the ground."""

    def __init__(self, entity: Player):
        super().__init__(
            entity,
            exit_resolver=self._hurt_exit,
            tags=["hurt", "invincible"],
            on_enter=self._hurt_enter,
        )

    def _hurt_enter(self, **kwargs: object) -> None:
        """Clear the dash request and apply the light knockback impulse."""
        self.entity.dash.cancel_request()

        knockback_dir = cast("int", kwargs.get("knockback_direction", 0))
        knockback_force = cast("float", kwargs.get("knockback_force", 0))
        if knockback_dir != 0 and knockback_force > 0:
            self.entity.velocity.x = knockback_dir * knockback_force

    def _hurt_exit(self) -> str | None:
        """Transition to stagger if pending, otherwise to the ground state."""
        if self.entity.stagger_timer > 0:
            return "stagger"
        return player_ground_return(self.entity)


class PlayerKnockbackState(KnockbackState["Player"]):
    """Player knockback reaction: strong launch, then ground recovery."""

    def __init__(self, entity: Player):
        super().__init__(
            entity,
            exit_resolver=self._knockback_exit,
            tags=["knockback", "invincible"],
            on_enter=self._knockback_enter,
        )

    def _knockback_enter(self, **kwargs: object) -> None:
        """Clear the dash request before the launch velocity is applied."""
        self.entity.dash.cancel_request()

    def _knockback_exit(self) -> str:
        """Recover through hurt if still hurt, otherwise to the ground state."""
        if self.entity.combat.is_hurt:
            return "hurt"
        return player_ground_return(self.entity)


class PlayerDashState(PlayerBaseState):
    snapshot_fields = ("direction", "reversed")

    """The dash: a burst that eases into the run, the same length every time.

    The speed follows one curve, from ``dash.speed`` at the press down to the
    exit speed at the end (``Physics.DASH_CURVE``): the run speed when the
    stick still points the way of the dash, so the dash hands over to the run
    without a stop, or ``Physics.DASH_EXIT_IDLE`` when it does not, a short
    glide the ground then stops. The way is chosen at the press; a push the
    other way in the first ``Physics.DASH_REVERSE_WINDOW`` turns it round,
    once -- a press read a frame late is still the player's.

    It used to hold full speed for as long as the stick was held and decay
    fast when it was not, so the same press went 180 px or 64 px, and it set
    the speed to zero on its last frame, which the run then had to climb back
    from: a stop in the middle of every dash-into-run.
    """

    def __init__(self, entity: Player):
        """Initialize the PlayerDashState instance with dashing tags."""
        super().__init__(entity, tags=["dash", "invincible"])
        self.direction = 1.0
        self.reversed = False

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        """Enter the state, consume dash charge, and squish hitbox."""
        self.entity.open_dodge_window()
        self.entity.dash.consume_charge()
        self.entity.dash.apply_squish(self.entity.hitbox)
        # The way of the press, else the stick now, else the facing.
        request_axis = self.entity.dash.request_move_axis
        move_axis = request_axis if request_axis != 0.0 else self.entity.move_axis
        if move_axis > 0:
            self.direction = 1.0
        elif move_axis < 0:
            self.direction = -1.0
        else:
            self.direction = 1.0 if self.entity.facing_right else -1.0
        self.reversed = False
        self.entity.velocity.x = self.entity.dash.speed * self.direction
        self.entity.velocity.y = 0.0
        self.entity.dash.duration_timer = self.entity.dash.duration
        # Signal dash start for screen shake/trauma
        self.entity.dash_started_this_frame = True

    def exit(self, next_state: str | None = None) -> None:
        """Exit the state and restore the original hitbox width."""
        if self.entity.dash.restore_hitbox(self.entity.hitbox):
            self.entity.handle_collisions("horizontal")
            self.entity.sync_rects()
        # Start dash coyote window for attack/guard after dash ends
        self.entity.dash.start_coyote()

    def _exit_speed(self) -> float:
        """The run speed while the stick holds the dash's way, a short glide otherwise."""
        if self.entity.move_axis * self.direction > 0.0:
            return float(self.entity.speed)
        return Physics.DASH_EXIT_IDLE

    def update(self, delta_time: float) -> str | None:
        """Follow the speed curve, turn round on an early push back, bounce off walls."""
        dash = self.entity.dash
        dash.duration_timer -= delta_time
        elapsed = dash.duration - dash.duration_timer
        if (
            not self.reversed
            and elapsed <= Physics.DASH_REVERSE_WINDOW
            and self.entity.move_axis * self.direction < 0.0
        ):
            self.direction = -self.direction
            self.reversed = True
            self.entity.facing_right = self.direction > 0.0
        share = min(1.0, max(0.0, elapsed / max(dash.duration, 1e-6)))
        exit_speed = self._exit_speed()
        speed = exit_speed + (dash.speed - exit_speed) * (1.0 - share) ** Physics.DASH_CURVE
        self.entity.velocity.x = speed * self.direction

        # Wall bounce: if dashing into a wall, bounce off with momentum retention
        if self.entity.on_surface.get("left", False) and self.direction < 0:
            self.direction = 1.0
            self.entity.velocity.x = -self.entity.velocity.x * Physics.DASH_WALL_BOUNCE
            self.entity.facing_right = True
        elif self.entity.on_surface.get("right", False) and self.direction > 0:
            self.direction = -1.0
            self.entity.velocity.x = -self.entity.velocity.x * Physics.DASH_WALL_BOUNCE
            self.entity.facing_right = False

        self.entity.velocity.y += self.entity.normal_gravity * dash.gravity_mult * delta_time
        if dash.duration_timer <= 0:
            # The exit speed is kept: the run picks it up, or the ground stops it.
            self.entity.velocity.x = exit_speed * self.direction
            return self.ground_return()
        return None


class PlayerStaggerState(StaggerState["Player"]):
    """Represent the PlayerStagger state."""

    def __init__(self, entity: Player):
        """Initialize the PlayerStaggerState instance with stagger tags."""
        super().__init__(
            entity,
            exit_resolver=lambda: player_ground_return(self.entity),
            tags=["stagger", "busy"],
        )


class PlayerDizzyState(State["Player"]):
    """Stunned by a full stun gauge; the shipped player has no gauge and never is."""

    def __init__(self, entity: Player):
        super().__init__(entity, tags=["dizzy", "busy"])

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        duration = cast("float", kwargs.get("duration", 0.0))
        if duration > 0:
            self.entity.stagger_timer = duration

    def update(self, delta_time: float) -> str | None:
        apply_reaction_drag(self.entity, delta_time)
        if self.entity.stagger_timer <= 0:
            return player_ground_return(self.entity)
        return None


class PlayerState(str, Enum):
    """Player-facing subset of the canonical state vocabulary.

    Values are literals because mypy types ``.value`` as ``str`` only for
    literal enum values. ``test_state_names`` checks every one against
    :class:`~src.shared.state_names.StateName`, so they cannot drift.
    """

    IDLE = "idle"
    WALK_SLOW = "walk_slow"
    WALK = "walk"
    RUN = "run"
    TURN = "turn"
    JUMP = "jump"
    FALL = "fall"
    WALL_SLIDE = "wall_slide"
    ATTACK = "attack"
    GUARD = "guard"
    HURT = "hurt"
    DASH = "dash"
    STAGGER = "stagger"
    CHARGE = "charge"
    RECHARGE = "recharge"
    PROMPT = "prompt"
    KNOCKBACK = "knockback"
    DIZZY = "dizzy"


def dash_cancel_open(player: Player) -> bool:
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


def _can_dash(player: Player) -> bool:
    """Check if the player can currently interrupt to dash."""
    return player.dash.can_use() and player.state_machine.current_state_name not in (
        PlayerState.DASH,
        PlayerState.HURT,
        PlayerState.KNOCKBACK,
        PlayerState.STAGGER,
    )


#: Movement in the guard, as a share of the fighter's speed.
GUARD_MOVE_MULT = 0.35

#: The states the guard and the recharge can be entered from: the fighter is
#: on its feet and doing nothing else.
_FREE_STATES = (
    PlayerState.IDLE,
    PlayerState.WALK_SLOW,
    PlayerState.WALK,
    PlayerState.RUN,
    PlayerState.TURN,
)


def _wants_guard(player: Player) -> bool:
    return bool(player.guard_held) and bool(player.on_surface.get("floor", False))


def _wants_recharge(player: Player) -> bool:
    return _wants_guard(player) and bool(player.down_held)


def _can_guard(player: Player) -> bool:
    """Whether the guard may be raised: held, on the floor, and free to."""
    if not _wants_guard(player) or _wants_recharge(player):
        return False
    return player.state_machine.current_state_name in _FREE_STATES


def _can_recharge(player: Player) -> bool:
    """Whether the recharge may begin: guard and Down held, from the guard or free."""
    if not _wants_recharge(player):
        return False
    current = player.state_machine.current_state_name
    return current in _FREE_STATES or current == PlayerState.GUARD


def _can_attack_interrupt(player: Player) -> bool:
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


def configure_player_state_machine(player: Player) -> None:
    """Build the player's state machine and its interrupts."""
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
    sm.add_state(PlayerState.GUARD, PlayerGuardState(player))
    sm.add_state(PlayerState.RECHARGE, PlayerRechargeState(player))
    sm.add_state(PlayerState.PROMPT, PlayerPromptState(player))
    sm.add_state(PlayerState.HURT, PlayerHurtState(player))
    sm.add_state(PlayerState.KNOCKBACK, PlayerKnockbackState(player))
    sm.add_state(PlayerState.DASH, PlayerDashState(player))
    sm.add_state(PlayerState.STAGGER, PlayerStaggerState(player))
    sm.add_state(PlayerState.DIZZY, PlayerDizzyState(player))
    sm.set_initial_state(PlayerState.IDLE)
    sm.add_interrupt(PlayerState.DASH, lambda: _can_dash(player), priority=80)
    sm.add_interrupt(PlayerState.PROMPT, lambda: player.prompt.active, priority=120)
    sm.add_interrupt(PlayerState.GUARD, lambda: _can_guard(player), priority=60)
    sm.add_interrupt(PlayerState.RECHARGE, lambda: _can_recharge(player), priority=61)
    sm.add_interrupt(PlayerState.ATTACK, lambda: _can_attack_interrupt(player), priority=40)
