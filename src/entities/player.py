import math
from collections.abc import Iterable, Sequence
from typing import Any

import pygame
from pygame.sprite import Group

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.attack_loading import load_attacks
from src.combat.combat_component import CombatComponent
from src.combat.knockback import KnockbackConfig
from src.core.colors import Colors
from src.core.input_manager import InputManager
from src.core.settings import Combat as CombatSettings
from src.core.settings import Physics
from src.entities.entity import Entity
from src.physics import apply_horizontal_movement, resolve_jump
from src.states.player_states import (
    PlayerAttackState,
    PlayerBlockState,
    PlayerDashState,
    PlayerFallState,
    PlayerHurtState,
    PlayerIdleState,
    PlayerJumpState,
    PlayerRunState,
    PlayerStaggerState,
    PlayerWallSlideState,
)
from src.states.state_machine import StateMachine

ATTACK_FORBIDDEN_STATES = {"wall_slide", "block", "hurt", "dash", "stagger"}


class Player(Entity):
    """
    Playable character with full state machine, input reading, and combat.

    Extends Entity with movement, jumping, dashing, blocking, and attacks.
    """

    def __init__(
        self,
        pos: tuple[float, float] | pygame.math.Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        moving_platforms: Iterable[Any],
        input_manager: InputManager,
    ) -> None:
        """
        Initialise the player.

        Args:
            pos: Starting position.
            groups: Sprite groups to add to.
            collision_sprites: Collision group.
            moving_platforms: Platforms that can carry the player.
            input_manager: Input source.
        """
        super().__init__(
            pos,
            (48.0, 56.0),
            Colors.green,
            groups,
            collision_sprites,
            hitbox_inflate=(-8.0, 0.0),
            health=100.0,
            max_health=100.0,
            faction="player",
            spawn_pos=pos,
            combat=None,
        )

        self.combat = CombatComponent(
            self,
            combo_window=CombatSettings.COMBO_WINDOW,
            hurt_duration=CombatSettings.PLAYER_HURT_DURATION,
        )
        load_attacks(self.combat, PLAYER_ATTACKS)

        self.speed = float(Physics.PLAYER_SPEED)
        self.floor_control = Physics.FLOOR_CONTROL
        self.air_control = Physics.AIR_CONTROL

        self.jump_height = float(Physics.JUMP_FORCE)
        self.wall_jump_height = float(Physics.JUMP_FORCE) * 0.90 * 1.15
        self.wall_jump_push_multiplier = 1.3
        self.wall_jump_lock_duration = 0.18
        self.wall_jump_min_lock = 0.08
        self.wall_slide_speed = Physics.WALL_SLIDE_SPEED

        self.max_midair_jumps = 1
        self.midair_jumps_left = self.max_midair_jumps
        self.max_wall_jumps = math.inf
        self.wall_jumps_left = self.max_wall_jumps

        self.space_held = False
        self.left_held = False
        self.right_held = False
        self.block_held = False
        self.move_axis = 0.0

        self.coyote_timer = 0.0
        self.coyote_duration = Physics.COYOTE_DURATION

        self.jump_buffer_timer = 0.0
        self.jump_buffer_duration = Physics.JUMP_BUFFER_DURATION

        self.moving_platforms = moving_platforms

        self.max_block_stamina = Physics.MAX_BLOCK_STAMINA
        self.block_stamina = self.max_block_stamina
        self.block_cooldown_timer = 0.0

        self.max_dash_charges = Physics.DASH_MAX_CHARGES
        self.dash_charges = self.max_dash_charges
        self.dash_recharge_timer = 0.0
        self.dash_penalty_timer = 0.0
        self.dash_speed = Physics.DASH_SPEED
        self.dash_duration = Physics.DASH_DURATION
        self.dash_friction = Physics.DASH_FRICTION
        self.dash_penalty_duration = Physics.DASH_PENALTY_TIME
        self._dash_duration_timer = 0.0
        self._original_hitbox_width = self.hitbox.width

        self.invincibility_timer = 0.0
        self._dash_requested = False

        self.state_machine = StateMachine(self)
        self.state_machine.add_state("idle", PlayerIdleState(self))
        self.state_machine.add_state("run", PlayerRunState(self))
        self.state_machine.add_state("jump", PlayerJumpState(self))
        self.state_machine.add_state("fall", PlayerFallState(self))
        self.state_machine.add_state("wall_slide", PlayerWallSlideState(self))
        self.state_machine.add_state("attack", PlayerAttackState(self))
        self.state_machine.add_state("block", PlayerBlockState(self))
        self.state_machine.add_state("hurt", PlayerHurtState(self))
        self.state_machine.add_state("dash", PlayerDashState(self))
        self.state_machine.add_state("stagger", PlayerStaggerState(self))
        self.state_machine.set_initial_state("idle")

        sm = self.state_machine
        sm.add_interrupt(
            "hurt",
            lambda: self.combat.is_hurt,
            priority=100,
        )
        sm.add_interrupt(
            "dash",
            lambda: (
                self._dash_requested
                and self.dash_charges > 0
                and sm.current_state_name not in ("dash", "hurt", "stagger")
            ),
            priority=80,
        )
        sm.add_interrupt(
            "block",
            lambda: (
                self.on_surface["floor"]
                and self.block_held
                and self.block_cooldown_timer <= 0
                and self.block_stamina > 0.3
                and sm.current_state_name not in ("wall_slide", "hurt", "dash", "stagger")
            ),
            priority=60,
        )
        sm.add_interrupt(
            "attack",
            lambda: self.combat.is_attacking and self.can_attack(),
            priority=40,
        )

        self.input_manager = input_manager

    @property
    def is_blocking(self) -> bool:
        """Return True if the player is currently blocking."""
        return self.state_machine.current_state_name == "block"

    def can_attack(self) -> bool:
        """Return True if an attack can be started from the current state."""
        return self.state_machine.current_state_name not in ATTACK_FORBIDDEN_STATES

    def _is_wall_sliding(self) -> bool:
        """Return True when sliding down a wall."""
        on_left_wall = self.on_surface["left"] and self.left_held
        on_right_wall = self.on_surface["right"] and self.right_held
        return (
            not self.on_surface["floor"]
            and (on_left_wall or on_right_wall)
            and self.velocity.y > 0
        )

    def _on_floor_contact(self) -> None:
        """Reset midair and wall jumps when landing."""
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def _on_wall_contact(self) -> None:
        """Reset midair jumps when touching a wall."""
        self.midair_jumps_left = self.max_midair_jumps

    def get_input(self) -> None:
        """Read all input and update facing direction and buffers."""
        im = self.input_manager
        self.move_axis = im.move_axis
        self.left_held = im.left_held
        self.right_held = im.right_held
        self.block_held = im.block_held

        if self.move_axis > 0.1:
            self.facing_right = True
        elif self.move_axis < -0.1:
            self.facing_right = False

        if im.jump_just_pressed:
            self.jump_buffer_timer = self.jump_buffer_duration

        if im.dash_just_pressed:
            if self.dash_charges > 0 and self.dash_penalty_timer <= 0:
                self._dash_requested = True
            else:
                self._dash_requested = False

        if im.reset_just_pressed:
            self.reset_position()

    def _handle_attack_input(self) -> None:
        """Start the appropriate attack based on input and state."""
        if not self.can_attack():
            return

        im = self.input_manager
        if im.attack1_just_pressed:
            if self.on_surface["floor"]:
                attack_name = "light_attack"
            else:
                attack_name = "air_attack"
            self.combat.start_attack(attack_name, self.facing_right)
        elif im.attack2_just_pressed:
            self.combat.start_attack("heavy_attack", self.facing_right)
        elif im.attack3_just_pressed:
            self.combat.start_attack("uppercut", self.facing_right)
        elif im.attack4_just_pressed:
            self.combat.start_attack("dash_attack", self.facing_right)

    def update_timers(self, delta_time: float) -> None:
        """Update coyote, jump buffer, block stamina, and dash recharge timers."""
        if self.jump_buffer_timer > 0:
            self.jump_buffer_timer -= delta_time

        if self.on_surface["floor"]:
            self.coyote_timer = self.coyote_duration
        elif self.coyote_timer > 0:
            self.coyote_timer -= delta_time

        if self.block_cooldown_timer > 0:
            self.block_cooldown_timer -= delta_time

        if self.state_machine.current_state_name != "block":
            if self.block_stamina < self.max_block_stamina:
                self.block_stamina += delta_time * 0.5
                self.block_stamina = min(
                    self.block_stamina, self.max_block_stamina)

        if self.dash_penalty_timer > 0:
            self.dash_penalty_timer -= delta_time
        else:
            if self.dash_charges < self.max_dash_charges:
                self.dash_recharge_timer -= delta_time
                if self.dash_recharge_timer <= 0:
                    self.dash_charges += 1
                    self.dash_recharge_timer = Physics.DASH_RECHARGE_TIME

    def apply_horizontal_movement(self, delta_time: float) -> None:
        """Apply horizontal acceleration/control."""
        apply_horizontal_movement(self, delta_time)

    def handle_jump(self) -> None:
        """Process jump input with coyote time, wall jumps, and midair jumps."""
        resolve_jump(self)

    def reset_position(self) -> None:
        """Full reset of all player‑specific state."""
        super().reset_position()
        self.jump_buffer_timer = 0.0
        self.coyote_timer = 0.0
        self.move_axis = 0.0
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps
        self.block_stamina = self.max_block_stamina
        self.block_cooldown_timer = 0.0
        self.dash_charges = self.max_dash_charges
        self.dash_recharge_timer = 0.0
        self.dash_penalty_timer = 0.0
        self._dash_requested = False
        self.invincibility_timer = 0.0
        self.hitbox.width = self._original_hitbox_width

        self.combat.state.end()
        self.combat.hitbox.clear()

    def respawn(self) -> None:
        """Alias for reset_position, used after death."""
        self.reset_position()

    def _apply_block_damage_reaction(
        self,
        amount: int,
        knockback: KnockbackConfig | None,
        source_center_x: float | None,
    ) -> None:
        """
        Handle damage while blocking: consume stamina, reduce knockback, and apply reduced push.
        """
        _kb = knockback if knockback is not None else KnockbackConfig()
        self.block_stamina -= amount * CombatSettings.BLOCK_STAMINA_COST_RATIO
        if self.block_stamina < 0:
            self.block_stamina = 0.0

        if _kb.mode == "fixed":
            self.velocity.x = _kb.power[0] * \
                CombatSettings.BLOCK_KNOCKBACK_FACTOR
        elif source_center_x is not None:
            direction = 1.0 if self.hitbox.centerx >= source_center_x else -1.0
            self.velocity.x = _kb.power[0] * \
                CombatSettings.BLOCK_KNOCKBACK_FACTOR * direction

    def receive_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
    ) -> None:
        """
        Override to add blocking, invincibility, and reduced hurt duration.

        If blocking, stamina is consumed and knockback is reduced; no health lost.
        If invincible (from being hit), damage is ignored.
        Otherwise, delegate to the base implementation and reduce hurt duration.
        """
        if self.is_dead:
            return

        if self.invincibility_timer > 0:
            return

        if self.is_blocking:
            self._apply_block_damage_reaction(
                amount, knockback, source_center_x)
            return

        super().receive_damage(amount, source_center_x, knockback, interrupt)

        if interrupt and self.combat._hurt_timer > 0:
            self.combat._hurt_timer = min(
                self.combat._hurt_timer,
                CombatSettings.PLAYER_HURT_DURATION,
            )

        self.invincibility_timer = CombatSettings.INVINCIBILITY_DURATION

    def update(self, delta_time: float) -> None:
        """Main update loop: input, timers, combat, state machine, and movement."""
        if self.is_dead:
            return

        super().update(delta_time)

        if self.invincibility_timer > 0:
            self.invincibility_timer -= delta_time
            if self.invincibility_timer < 0:
                self.invincibility_timer = 0.0

        self.get_input()
        self._handle_attack_input()
        self.update_timers(delta_time)
        self.combat.update(delta_time, self.facing_right)
        self.state_machine.update(delta_time)
        self.move(delta_time)
