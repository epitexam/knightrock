"""Player capability controllers extracted from ``Player`` (ARCH-03).

``Player`` used to own every timer, counter, and configuration mirror of
its dash, block, and jump mechanics inline (40+ attributes).  Each
mechanic now lives in a dedicated controller that owns its timers and
exposes ``can_use()`` / ``update(dt)``.  ``Player`` composes the three
controllers and delegates to them, while keeping flat property access
for the physics protocols (``JumpEntity``, ``WallJumpLock``), the debug
UI, and the states.

Each controller is deliberately ignorant of the state machine and of
``Player`` itself: orchestration flags (``on_floor``, ``is_blocking``)
are passed in by the caller, mirroring the ``Vitals`` design.
"""

import pygame

from src.entities.player_config import PlayerConfig

BLOCK_MIN_STAMINA = 0.3
"""Minimum stamina required before a block can be entered."""

BLOCK_STAMINA_REGEN_RATE = 0.5
"""Stamina points regenerated per second while not actively blocking."""

DASH_HITBOX_SQUISH = 0.6
"""Hitbox width multiplier applied while dashing."""


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


class BlockController:
    """Own block resources: stamina pool and post-block cooldown.

    Parameters
    ----------
    config : PlayerConfig
        Source of the block tuning values.
    """

    def __init__(self, config: PlayerConfig) -> None:
        self.max_block_stamina: float = config.max_block_stamina
        self.block_cooldown_normal: float = config.block_cooldown_normal
        self.block_cooldown_broken: float = config.block_cooldown_broken

        self.block_stamina: float = self.max_block_stamina
        self.block_cooldown_timer: float = 0.0

    def can_use(self) -> bool:
        """Whether blocking may be entered (off cooldown, enough stamina)."""
        return (
            self.block_cooldown_timer <= 0
            and self.block_stamina > BLOCK_MIN_STAMINA
        )

    def update(self, delta_time: float, is_blocking: bool) -> None:
        """Decay the cooldown and regenerate stamina while not blocking."""
        if self.block_cooldown_timer > 0:
            self.block_cooldown_timer -= delta_time

        if not is_blocking and self.block_stamina < self.max_block_stamina:
            self.block_stamina = min(
                self.block_stamina + delta_time * BLOCK_STAMINA_REGEN_RATE,
                self.max_block_stamina,
            )

    def consume(self, amount: float) -> None:
        """Spend stamina, clamped at zero (a broken guard)."""
        self.block_stamina -= amount
        if self.block_stamina < 0:
            self.block_stamina = 0.0

    def apply_exit_cooldown(self) -> None:
        """Arm the cooldown due after leaving the block state.

        A guard broken by stamina exhaustion triggers the longer
        ``block_cooldown_broken``; otherwise ``block_cooldown_normal``.
        """
        if self.block_stamina <= 0:
            self.block_cooldown_timer = self.block_cooldown_broken
        else:
            self.block_cooldown_timer = self.block_cooldown_normal

    def reset(self) -> None:
        """Restore the stamina pool and clear the cooldown."""
        self.block_stamina = self.max_block_stamina
        self.block_cooldown_timer = 0.0


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
        self.duration_timer: float = 0.0
        self.original_hitbox_width: float = original_hitbox_width

    def can_use(self) -> bool:
        """Whether a pending dash request can actually start a dash."""
        return self.requested and self.charges > 0

    def request(self) -> None:
        """Register a dash press, gated by available charges and penalty."""
        self.requested = self.charges > 0 and self.penalty_timer <= 0

    def cancel_request(self) -> None:
        """Drop any pending dash request (hit, knockback, dash started)."""
        self.requested = False

    def consume_charge(self) -> None:
        """Spend one charge and arm recharge/penalty timers accordingly."""
        self.charges -= 1
        self.requested = False
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