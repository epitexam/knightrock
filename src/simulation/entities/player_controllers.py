"""The player's jump and dash: each controller owns its timers and its snapshot."""

from dataclasses import dataclass

import pygame

from src.simulation.entities.player_config import PlayerConfig

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
class DashSnapshot:
    """Serializable capture of the dash controller's runtime state."""

    charges: int
    recharge_timer: float
    penalty_timer: float
    requested: bool
    request_move_axis: float
    duration_timer: float
    coyote_timer: float
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
        """Capture runtime state for rollback."""
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
        self.penalty_duration: float = config.dash_penalty_duration
        self.recharge_time: float = config.dash_recharge_time
        self.gravity_mult: float = config.dash_gravity_mult
        self.coyote_time: float = config.dash_coyote_time

        self.charges: int = self.max_charges
        self.recharge_timer: float = 0.0
        self.penalty_timer: float = 0.0
        self.requested: bool = False
        self.request_move_axis: float = 0.0
        self.duration_timer: float = 0.0
        self.coyote_timer: float = 0.0
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

    def refill(self) -> None:
        """Give every charge back at once, and lift the penalty for having spent them all."""
        self.charges = self.max_charges
        self.recharge_timer = 0.0
        self.penalty_timer = 0.0

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

        # Dash coyote timer: allows attack/guard for a short window after dash ends
        if self.coyote_timer > 0:
            self.coyote_timer -= delta_time

    def start_coyote(self) -> None:
        """Start the dash coyote window (call when dash ends)."""
        self.coyote_timer = self.coyote_time

    def in_coyote(self) -> bool:
        """Check if in dash coyote window."""
        return self.coyote_timer > 0

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
        self.coyote_timer = 0.0

    def save_state(self) -> DashSnapshot:
        """Capture runtime state for rollback."""
        return DashSnapshot(
            charges=self.charges,
            recharge_timer=self.recharge_timer,
            penalty_timer=self.penalty_timer,
            requested=self.requested,
            request_move_axis=self.request_move_axis,
            duration_timer=self.duration_timer,
            coyote_timer=self.coyote_timer,
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
        self.coyote_timer = snapshot.coyote_timer
        self.original_hitbox_width = snapshot.original_hitbox_width
