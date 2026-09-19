"""Player capability controllers extracted from ``Player``.

``Player`` composes jump, guard, and dash mechanics. Each controller owns
its timers and exposes ``can_use`` / ``update``. ``Player`` passes
orchestration flags (``on_floor``, ``is_guarding``) in by the caller.
"""

from dataclasses import dataclass

import pygame

from src.core.settings import Guard as GuardSettings
from src.entities.player_config import PlayerConfig

DASH_HITBOX_SQUISH = 0.6
"""Hitbox width multiplier applied while dashing."""


@dataclass(frozen=True)
class JumpSnapshot:
    """Serializable capture of the jump controller's runtime state."""

    jump_buffer_timer: float
    coyote_timer: float
    wall_jump_lock_timer: float
    midair_jumps_left: int
    wall_jumps_left: int | float


@dataclass(frozen=True)
class GuardSnapshot:
    posture: float
    lockout_timer: float
    parry_timer: float
    riposte_timer: float


@dataclass(frozen=True)
class DashSnapshot:
    """Serializable capture of the dash controller's runtime state."""

    charges: int
    recharge_timer: float
    penalty_timer: float
    requested: bool
    request_move_axis: float
    duration_timer: float
    original_hitbox_width: float


class JumpController:
    """Own jump resources: buffer, coyote time, wall lock, and jump stocks.

    Parameters
    ----------
    config : PlayerConfig
        Source of the jump tuning values.
    """

    def __init__(self, config: PlayerConfig) -> None:
        self.jump_height: float = config.jump_height
        self.wall_jump_height: float = config.wall_jump_height
        self.wall_jump_push_multiplier: float = config.wall_jump_push_multiplier
        self.wall_jump_lock_duration: float = config.wall_jump_lock_duration
        self.wall_jump_min_lock: float = config.wall_jump_min_lock
        self.wall_slide_speed: float = config.wall_slide_speed
        self.coyote_duration: float = config.coyote_duration
        self.jump_buffer_duration: float = config.jump_buffer_duration
        self.max_midair_jumps: int = config.max_midair_jumps
        self.max_wall_jumps: int | float = config.max_wall_jumps

        self.jump_buffer_timer: float = 0.0
        self.coyote_timer: float = 0.0
        self.wall_jump_lock_timer: float = 0.0
        self.midair_jumps_left: int = self.max_midair_jumps
        self.wall_jumps_left: int | float = self.max_wall_jumps

    def has_buffered_jump(self) -> bool:
        """Whether a jump press is waiting to be consumed."""
        return self.jump_buffer_timer > 0

    def buffer_press(self) -> None:
        """Arm the jump buffer after a jump input."""
        self.jump_buffer_timer = self.jump_buffer_duration

    def update(self, delta_time: float, on_floor: bool) -> None:
        """Decay the buffer and refresh or decay the coyote window."""
        if self.jump_buffer_timer > 0:
            self.jump_buffer_timer -= delta_time

        if on_floor:
            self.coyote_timer = self.coyote_duration
        elif self.coyote_timer > 0:
            self.coyote_timer -= delta_time

    def restore_ground_jumps(self) -> None:
        """Refill every jump stock after touching the floor."""
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def restore_midair_jumps(self) -> None:
        """Refill midair jumps after touching a wall."""
        self.midair_jumps_left = self.max_midair_jumps

    def reset(self) -> None:
        """Clear timers and restore all jump stocks."""
        self.jump_buffer_timer = 0.0
        self.coyote_timer = 0.0
        self.wall_jump_lock_timer = 0.0
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def save_state(self) -> JumpSnapshot:
        """Capture runtime state for rollback (Phase 3 #3)."""
        return JumpSnapshot(
            jump_buffer_timer=self.jump_buffer_timer,
            coyote_timer=self.coyote_timer,
            wall_jump_lock_timer=self.wall_jump_lock_timer,
            midair_jumps_left=self.midair_jumps_left,
            wall_jumps_left=self.wall_jumps_left,
        )

    def load_state(self, snapshot: JumpSnapshot) -> None:
        """Restore runtime state from a rollback snapshot."""
        self.jump_buffer_timer = snapshot.jump_buffer_timer
        self.coyote_timer = snapshot.coyote_timer
        self.wall_jump_lock_timer = snapshot.wall_jump_lock_timer
        self.midair_jumps_left = snapshot.midair_jumps_left
        self.wall_jumps_left = snapshot.wall_jumps_left


class GuardController:
    """Directional guard posture with a parry window and break lockout."""

    def __init__(self, config: PlayerConfig) -> None:
        self.max_posture: float = config.guard_posture_max
        self.break_lockout: float = config.guard_break_lockout
        self.posture: float = self.max_posture
        self.lockout_timer: float = 0.0
        self.parry_timer: float = 0.0
        self.riposte_timer: float = 0.0

    def can_use(self) -> bool:
        return self.lockout_timer <= 0 and self.posture > 0

    def press(self) -> None:
        if self.lockout_timer <= 0:
            self.parry_timer = GuardSettings.PARRY_WINDOW

    def update(self, delta_time: float, is_guarding: bool) -> None:
        if self.lockout_timer > 0:
            self.lockout_timer -= delta_time
        if self.parry_timer > 0:
            self.parry_timer -= delta_time
        if self.riposte_timer > 0:
            self.riposte_timer -= delta_time
        if not is_guarding and self.posture < self.max_posture:
            self.posture = min(
                self.posture + delta_time * GuardSettings.REGEN_PER_S,
                self.max_posture,
            )

    def take_hit(self, amount: float, in_air: bool) -> tuple[str, float, bool]:
        if self.parry_timer > 0:
            self.posture = self.max_posture
            self.riposte_timer = GuardSettings.RIPOSTE_WINDOW
            self.parry_timer = 0.0
            return ("parry", 0.0, True)
        mult = GuardSettings.AIR_POSTURE_MULT if in_air else 1.0
        self.posture -= amount * GuardSettings.POSTURE_COST_RATIO * mult
        chip = amount * GuardSettings.CHIP_RATIO
        if self.posture <= 0:
            self.posture = 0.0
            self.lockout_timer = self.break_lockout
            self.riposte_timer = 0.0
            return ("break", chip, False)
        return ("guard", chip, False)

    def reset(self) -> None:
        self.posture = self.max_posture
        self.lockout_timer = 0.0
        self.parry_timer = 0.0
        self.riposte_timer = 0.0

    def save_state(self) -> GuardSnapshot:
        return GuardSnapshot(
            posture=self.posture,
            lockout_timer=self.lockout_timer,
            parry_timer=self.parry_timer,
            riposte_timer=self.riposte_timer,
        )

    def load_state(self, snapshot: GuardSnapshot) -> None:
        self.posture = snapshot.posture
        self.lockout_timer = snapshot.lockout_timer
        self.parry_timer = snapshot.parry_timer
        self.riposte_timer = snapshot.riposte_timer


class DashController:
    """Own dash resources: charges, recharge, penalty, and squished hitbox.

    Parameters
    ----------
    config : PlayerConfig
        Source of the dash tuning values.
    original_hitbox_width : float
        Hitbox width captured at spawn; overwritten on every squish.
    """

    def __init__(
        self,
        config: PlayerConfig,
        original_hitbox_width: float = 0.0,
    ) -> None:
        self.max_charges: int = config.max_dash_charges
        self.speed: float = config.dash_speed
        self.duration: float = config.dash_duration
        self.friction: float = config.dash_friction
        self.penalty_duration: float = config.dash_penalty_duration
        self.recharge_time: float = config.dash_recharge_time
        self.gravity_mult: float = config.dash_gravity_mult

        self.charges: int = self.max_charges
        self.recharge_timer: float = 0.0
        self.penalty_timer: float = 0.0
        self.requested: bool = False
        self.request_move_axis: float = 0.0
        self.duration_timer: float = 0.0
        self.original_hitbox_width: float = original_hitbox_width

    def can_use(self) -> bool:
        """Whether a pending dash request can actually start a dash."""
        return self.requested and self.charges > 0

    def request(self, move_axis: float = 0.0) -> None:
        """Register a dash press, gated by available charges and penalty.

        Captures the move_axis at request time for reactive dash direction.
        """
        self.requested = self.charges > 0 and self.penalty_timer <= 0
        if self.requested:
            self.request_move_axis = move_axis

    def cancel_request(self) -> None:
        """Drop any pending dash request (hit, knockback, dash started)."""
        self.requested = False
        self.request_move_axis = 0.0

    def consume_charge(self) -> None:
        """Spend one charge and arm recharge/penalty timers accordingly."""
        self.charges -= 1
        self.requested = False
        self.request_move_axis = 0.0
        if self.recharge_timer <= 0:
            self.recharge_timer = self.recharge_time
        if self.charges == 0:
            self.penalty_timer = self.penalty_duration

    def update(self, delta_time: float) -> None:
        """Run the penalty window, then recharge spent charges."""
        if self.penalty_timer > 0:
            self.penalty_timer -= delta_time
        else:
            if self.charges < self.max_charges:
                self.recharge_timer -= delta_time
                if self.recharge_timer <= 0:
                    self.charges += 1
                    self.recharge_timer = self.recharge_time

    def apply_squish(self, hitbox: pygame.FRect) -> None:
        """Narrow the hitbox for the dash, keeping its horizontal center."""
        self.original_hitbox_width = hitbox.width
        new_width = self.original_hitbox_width * DASH_HITBOX_SQUISH
        hitbox.x += (self.original_hitbox_width - new_width) / 2
        hitbox.width = new_width

    def restore_hitbox(self, hitbox: pygame.FRect) -> bool:
        """Restore the squished width, re-centered; report a change."""
        current = hitbox.width
        if current == self.original_hitbox_width:
            return False
        hitbox.x -= (self.original_hitbox_width - current) / 2
        hitbox.width = self.original_hitbox_width
        return True

    def reset(self) -> None:
        """Refill charges and clear request and recharge/penalty timers."""
        self.charges = self.max_charges
        self.recharge_timer = 0.0
        self.penalty_timer = 0.0
        self.requested = False
        self.request_move_axis = 0.0

    def save_state(self) -> DashSnapshot:
        """Capture runtime state for rollback (Phase 3 #3)."""
        return DashSnapshot(
            charges=self.charges,
            recharge_timer=self.recharge_timer,
            penalty_timer=self.penalty_timer,
            requested=self.requested,
            request_move_axis=self.request_move_axis,
            duration_timer=self.duration_timer,
            original_hitbox_width=self.original_hitbox_width,
        )

    def load_state(self, snapshot: DashSnapshot) -> None:
        """Restore runtime state from a rollback snapshot."""
        self.charges = snapshot.charges
        self.recharge_timer = snapshot.recharge_timer
        self.penalty_timer = snapshot.penalty_timer
        self.requested = snapshot.requested
        self.request_move_axis = snapshot.request_move_axis
        self.duration_timer = snapshot.duration_timer
        self.original_hitbox_width = snapshot.original_hitbox_width
