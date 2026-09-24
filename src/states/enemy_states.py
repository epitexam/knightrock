"""State machine states for enemies (AI)."""

from enum import Enum
from typing import Any

from src.core.settings import AI, EnemyJump
from src.states.reaction_states import (
    HurtState,
    KnockbackState,
    StaggerState,
)
from src.states.state_machine import State


class EnemyState(str, Enum):
    """Enemy state names: typed equivalent of the player PlayerState.

    String-based for drop-in compatibility with StateMachine keys.
    """

    IDLE = "idle"
    PATROL = "patrol"
    CHASE = "chase"
    ATTACK = "attack"
    CHARGE = "charge"
    HURT = "hurt"
    KNOCKBACK = "knockback"
    STAGGER = "stagger"
    DIZZY = "dizzy"
    LEDGE = "ledge"


class EnemyIdleState(State):
    """Idle state: the enemy stands still for a short duration."""

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state and initialize the idle timer."""
        self.timer = self.entity.idle_duration

    def update(self, delta_time: float) -> str | None:
        """Update the state and transition to patrol or chase."""
        self.timer -= delta_time
        if self.timer <= 0:
            if self.entity.can_see_player():
                self.entity.state_machine.change_state(EnemyState.CHASE)
            else:
                self.entity.state_machine.change_state(EnemyState.PATROL)
        return None


class EnemyPatrolState(State):
    """Patrol state: the enemy moves back and forth in a single direction."""

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state and initialize patrol direction, timer, speed."""
        self.patrol_timer = self.entity.patrol_interval
        self.direction = self.entity.patrol_direction
        self.entity.speed = self.entity.patrol_speed

    def update(self, delta_time: float) -> str | None:
        """Update the state, move the enemy, and check for player detection."""
        # The axis leads: the ledge probe reads it, so it is set before
        # probing (facing may lag a turn behind and must not steer this).
        self.entity.move_axis = self.direction
        if self.entity.is_at_ledge():
            self.entity.state_machine.change_state(EnemyState.LEDGE)
            return None
        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.can_see_player():
            self.entity.state_machine.change_state(EnemyState.CHASE)
            return None

        self.patrol_timer -= delta_time
        if self.patrol_timer <= 0:
            self.direction *= -1
            self.patrol_timer = self.entity.patrol_interval
            self.entity.facing_right = self.direction > 0
        return None

    def exit(self, next_state: str | None = None) -> None:
        """Exit the state and reset movement axis."""
        self.entity.move_axis = 0.0


class EnemyChaseState(State):
    """Chase state: the enemy moves towards the player."""

    def __init__(self, entity: Any, tags: list[str] | None = None):
        """Initialize the chase with a ready jump cooldown."""
        super().__init__(entity, tags or [])
        # Rollback-safe by construction: plain scalars, auto-captured in
        # StateMachineSnapshot.state_attrs like every other state scalar.
        self.jump_cooldown_timer = 0.0
        self.leap_glide_timer = 0.0

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state, face the player, and pick up chase speed."""
        self.entity.face_player()
        self.entity.speed = self.entity.chase_speed
        self.leap_glide_timer = 0.0

    def update(self, delta_time: float) -> str | None:
        """Update the state, move towards the player, and check attack range."""
        if self.entity.player is None:
            self.entity.state_machine.change_state(EnemyState.IDLE)
            return None

        player_center = self.entity.player.hitbox.centerx
        enemy_center = self.entity.hitbox.centerx
        if abs(player_center - enemy_center) < AI.CHASE_STOP_DISTANCE_PX:
            self.entity.move_axis = 0.0
        else:
            self.entity.move_axis = 1.0 if player_center > enemy_center else -1.0
            self.entity.facing_right = self.entity.move_axis > 0

        jumped = self._try_jump(delta_time)
        at_ledge = self.entity.is_at_ledge()
        leapt = False
        if not jumped and at_ledge:
            leapt = self._try_gap_jump() or self._try_risky_jump()
            jumped = leapt or self._try_drop()
        if not jumped and at_ledge:
            self.entity.state_machine.change_state(EnemyState.LEDGE)
            return None

        if not leapt and not self._glide_step(delta_time):
            self.entity.apply_horizontal_movement(delta_time)

        if self.entity.is_player_in_range():
            self.entity.state_machine.change_state(EnemyState.ATTACK)
        elif not self.entity.can_see_player():
            self.entity.state_machine.change_state(EnemyState.IDLE)
        return None

    def _glide_step(self, delta_time: float) -> bool:
        """Ballistic leap flight: no air steering while the timer runs.

        The leap's sprint speed is only honest if nothing drags it back
        to cruise mid-flight, so steering pauses until touchdown (contacts
        clear the timer) or the computed air time expires.
        """
        if self.leap_glide_timer <= 0.0:
            return False
        if self.entity.on_surface.get("floor", False):
            self.leap_glide_timer = 0.0
            return False
        self.leap_glide_timer = max(0.0, self.leap_glide_timer - delta_time)
        return True

    def _try_jump(self, delta_time: float) -> bool:
        """Hop at a wall or up toward the player (jump-capable types only).

        A plain grounded impulse — no buffer, no coyote, no double jump:
        the full ``JumpEntity`` protocol stays a player privilege. Jumpers
        even clear gaps this way: a hop starts before the ledge guard runs,
        so airborne ledge checks stay quiet.
        """
        self.jump_cooldown_timer = max(0.0, self.jump_cooldown_timer - delta_time)
        entity = self.entity
        if (
            not getattr(entity, "can_jump", False)
            or float(getattr(entity, "jump_height", 0.0) or 0.0) <= 0.0
            or not entity.on_surface.get("floor", False)
            or self.jump_cooldown_timer > 0.0
        ):
            return False
        wall_ahead = (entity.move_axis > 0.0 and entity.on_surface.get("right", False)) or (
            entity.move_axis < 0.0 and entity.on_surface.get("left", False)
        )
        player = entity.player
        player_above = (
            player is not None
            and player.hitbox.bottom < entity.hitbox.top - EnemyJump.PLAYER_ABOVE_MARGIN_PX
            and abs(player.hitbox.centerx - entity.hitbox.centerx) < EnemyJump.SEEK_RANGE_PX
        )
        if not (wall_ahead or player_above):
            return False
        entity.velocity.y = -entity.jump_height
        self.jump_cooldown_timer = float(getattr(entity, "jump_cooldown", 1.0) or 0.0)
        return True

    def _try_gap_jump(self) -> bool:
        """Leap the void when the player waits on a reachable far side.

        Only at a ledge, only level with the player (chasing someone down
        a pit is suicide — the ledge guard turns instead), and only when a
        landing sits inside the physics-derived hop range. The horizontal
        chase axis already points across, so the flight carries over.
        """
        context = self._leap_context()
        player = self.entity.player
        if context is None or player is None:
            return False
        entity, direction, hop_range = context
        ahead = (player.hitbox.centerx - entity.hitbox.centerx) * direction
        if ahead <= 0.0 or ahead > self._sight_range(entity):
            return False
        if abs(player.hitbox.bottom - entity.hitbox.bottom) > EnemyJump.GAP_LEVEL_PX:
            return False
        safe_range = hop_range * EnemyJump.RANGE_SAFETY
        landing = entity.find_landing_ahead(
            safe_range,
            entity.jump_apex() * EnemyJump.RISE_SAFETY,
            EnemyJump.MAX_LANDING_DROP_PX,
        )
        if landing is None or landing[0] > safe_range:
            return False
        self._leap(entity, direction)
        return True

    def _leap_context(self) -> tuple[Any, float, float] | None:
        """Shared preconditions for void leaps: jumper, ready, grounded.

        Returns (entity, direction, hop_range) or None. The cooldown was
        already ticked by ``_try_jump`` this tick; every leap below honors
        it without re-ticking.
        """
        entity = self.entity
        if (
            not getattr(entity, "can_jump", False)
            or float(getattr(entity, "jump_height", 0.0) or 0.0) <= 0.0
            or self.jump_cooldown_timer > 0.0
            or entity.move_axis == 0.0
            or not entity.on_surface.get("floor", False)
        ):
            return None
        direction = 1.0 if entity.move_axis > 0.0 else -1.0
        return entity, direction, entity.jump_range()

    @staticmethod
    def _sight_range(entity: Any) -> float:
        """How far ahead the leap cares about the player: vision, else SEEK."""
        return float(getattr(entity, "vision_range", 0.0) or 0.0) or EnemyJump.SEEK_RANGE_PX

    def _leap(self, entity: Any, direction: float) -> None:
        """Fire the leap: vertical impulse plus a sprint boost forward.

        The boost is what carries running jumps past a standing hop's
        range — ``jump_range`` already counts it, and the glide timer
        below keeps air steering from dragging it back to cruise, so the
        brain only attempts leaps the legs can actually finish.
        """
        entity.velocity.y = -entity.jump_height
        entity.velocity.x = (
            direction * entity.speed * float(getattr(entity, "leap_speed_mult", 1.0) or 0.0)
        )
        self.jump_cooldown_timer = float(getattr(entity, "jump_cooldown", 1.0) or 0.0)
        self.leap_glide_timer = float(entity.leap_air_time())

    def _try_risky_jump(self) -> bool:
        """Leap a slightly-too-wide or slightly-too-deep gap anyway.

        The safe jump above already declined: the landing sits past the
        margined range (but inside the raw physics range) or drops deeper
        than ``MAX_LANDING_DROP_PX`` (but above ``RISK_DROP_PX``). Genuine
        gamble — drag or a short takeoff can still eat it — so it only
        fires with the player committed ahead, never blindly.
        """
        context = self._leap_context()
        player = self.entity.player
        if context is None or player is None:
            return False
        entity, direction, hop_range = context
        ahead = (player.hitbox.centerx - entity.hitbox.centerx) * direction
        if ahead <= 0.0 or ahead > self._sight_range(entity):
            return False
        depth = player.hitbox.bottom - entity.hitbox.bottom
        if depth < -entity.jump_apex() or depth > EnemyJump.RISK_DROP_PX:
            return False
        landing = entity.find_landing_ahead(
            hop_range,
            entity.jump_apex(),
            EnemyJump.RISK_DROP_PX,
        )
        if landing is None or landing[0] > hop_range:
            return False
        self._leap(entity, direction)
        return True

    def _try_drop(self) -> bool:
        """Walk off after a player below when a floor catches the fall.

        No impulse, no cooldown: the chase simply keeps walking and gravity
        does the rest. A bottomless probe (no landing within ``DROP_SEEK``)
        declines — that way lies the death border, and the ledge guard
        turns instead.
        """
        entity = self.entity
        player = entity.player
        if (
            player is None
            or not getattr(entity, "can_jump", False)
            or entity.move_axis == 0.0
            or not entity.on_surface.get("floor", False)
        ):
            return False
        direction = 1.0 if entity.move_axis > 0.0 else -1.0
        ahead = (player.hitbox.centerx - entity.hitbox.centerx) * direction
        if ahead <= 0.0 or ahead > self._sight_range(entity):
            return False
        depth = player.hitbox.bottom - entity.hitbox.bottom
        if depth <= 0.0 or depth > EnemyJump.DROP_SEEK_PX:
            return False
        return (
            entity.find_landing_ahead(EnemyJump.SEEK_RANGE_PX, 0.0, EnemyJump.DROP_SEEK_PX)
            is not None
        )


class EnemyAttackState(State):
    """Attack state: the enemy performs its attack."""

    def __init__(self, entity: Any, tags: list[str] | None = None):
        """Initialize the EnemyAttackState instance."""
        super().__init__(entity, tags or ["attack", "busy"])

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Enter the state, face the player, and start the attack."""
        self.entity.face_player()

        if self.entity.attack_name is not None:
            self.entity.combat.start_attack(self.entity.attack_name)
        self._started = True

    def update(self, delta_time: float) -> str | None:
        """Update the state and return to idle when the attack finishes."""
        if not self.entity.combat.is_attacking:
            self.entity.state_machine.change_state(EnemyState.IDLE)
        return None

    def exit(self, next_state: str | None = None) -> None:
        """Exit the state."""
        self._started = False


class EnemyChargeState(State):
    """Charge state: the enemy is charging an attack."""

    def __init__(self, entity: Any, tags: list[str] | None = None):
        """Initialize the EnemyChargeState instance."""
        super().__init__(entity, tags or ["charge", "busy"])

    def update(self, delta_time: float) -> str | None:
        """Update the state and transition to attack when charge is released."""
        if not self.entity.combat.charging.is_charging:
            if self.entity.combat.is_attacking:
                self.entity.state_machine.change_state(EnemyState.ATTACK)
            else:
                self.entity.state_machine.change_state(EnemyState.IDLE)
        return None


class EnemyHurtState(HurtState):
    """Hurt reaction: return to idle when the hurt timer clears.

    Shares the generic :class:`HurtState` logic (ARCH-05); enemies hold no
    knockback impulse and no friction on hurt.
    """

    def __init__(self, entity: Any):
        super().__init__(entity, exit_resolver=lambda: EnemyState.IDLE, tags=[])


class EnemyKnockbackState(KnockbackState):
    """Knockback reaction: return to hurt/idle when the enemy stops sliding."""

    def __init__(self, entity: Any):
        super().__init__(
            entity,
            exit_resolver=self._resolve_exit,
            tags=["knockback", "busy"],
            on_enter=self._clear_steering,
        )

    def _clear_steering(self, **kwargs: Any) -> None:
        """Drop the stale chase axis so corpses don't steer their own flight."""
        self.entity.move_axis = 0.0

    def _resolve_exit(self) -> str:
        """Recover through hurt if still hurt, otherwise to idle."""
        return EnemyState.HURT if self.entity.combat.is_hurt else EnemyState.IDLE


class EnemyStaggerState(StaggerState):
    """Stagger reaction: return to idle when the stagger timer clears."""

    def __init__(self, entity: Any):
        super().__init__(entity, exit_resolver=lambda: EnemyState.IDLE, tags=[])


class EnemyDizzyState(State):
    """Dizzy reaction from consecutive perfect parries: return to idle when timer clears."""

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
            return EnemyState.IDLE
        return None
