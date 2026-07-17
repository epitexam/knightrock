"""Player entity with full state machine, input reading, and combat mechanics."""

import math
from collections.abc import Iterable, Sequence
from enum import Enum
from typing import Any

import pygame
from pygame.sprite import Group

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.knockback import KnockbackConfig
from src.core.colors import Colors
from src.core.input_manager import InputManager
from src.core.settings import Combat as CombatSettings
from src.core.settings import Physics
from src.entities.entity import Entity, DamageResult, compute_knockback_direction
from src.physics import resolve_jump
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


class PlayerState(str, Enum):
    """Enumeration of player states for type safety and refactoring reliability."""
    IDLE = "idle"
    RUN = "run"
    JUMP = "jump"
    FALL = "fall"
    WALL_SLIDE = "wall_slide"
    ATTACK = "attack"
    BLOCK = "block"
    HURT = "hurt"
    DASH = "dash"
    STAGGER = "stagger"


ATTACK_FORBIDDEN_STATES = {
    PlayerState.WALL_SLIDE,
    PlayerState.BLOCK,
    PlayerState.HURT,
    PlayerState.DASH,
    PlayerState.STAGGER,
}
"""Set of states where initiating an attack is forbidden."""


class Player(Entity):
    """Playable character with full state machine, input reading, and combat.

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
        """Initialise the player.

        Parameters
        ----------
        pos : tuple[float, float] | pygame.math.Vector2
            Starting position.
        groups : Group | Sequence[Group]
            Sprite groups to add to.
        collision_sprites : Group
            Collision group.
        moving_platforms : Iterable[Any]
            Platforms that can carry the player.
        input_manager : InputManager
            Input source.
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
            attacks=PLAYER_ATTACKS,
            hurt_duration=CombatSettings.PLAYER_HURT_DURATION,
            invincibility_duration=CombatSettings.INVINCIBILITY_DURATION,
        )

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

        self._dash_requested = False

        self.input_manager = input_manager

        self._setup_state_machine()

    def _setup_state_machine(self) -> None:
        """Initialize the player-specific state machine and registers interrupts."""
        self.state_machine = StateMachine(self)
        self.state_machine.add_state(PlayerState.IDLE, PlayerIdleState(self))
        self.state_machine.add_state(PlayerState.RUN, PlayerRunState(self))
        self.state_machine.add_state(PlayerState.JUMP, PlayerJumpState(self))
        self.state_machine.add_state(PlayerState.FALL, PlayerFallState(self))
        self.state_machine.add_state(
            PlayerState.WALL_SLIDE, PlayerWallSlideState(self))
        self.state_machine.add_state(
            PlayerState.ATTACK, PlayerAttackState(self))
        self.state_machine.add_state(PlayerState.BLOCK, PlayerBlockState(self))
        self.state_machine.add_state(PlayerState.HURT, PlayerHurtState(self))
        self.state_machine.add_state(PlayerState.DASH, PlayerDashState(self))
        self.state_machine.add_state(
            PlayerState.STAGGER, PlayerStaggerState(self))
        self.state_machine.set_initial_state(PlayerState.IDLE)
        self._setup_interrupts()

    def _can_dash(self) -> bool:
        """Check if the player can currently interrupt to dash."""
        return (
            self._dash_requested
            and self.dash_charges > 0
            and self.state_machine.current_state_name not in (
                PlayerState.DASH, PlayerState.HURT, PlayerState.STAGGER
            )
        )

    def _can_block(self) -> bool:
        """Check if the player can currently interrupt to block."""
        return (
            self.on_surface["floor"]
            and self.block_held
            and self.block_cooldown_timer <= 0
            and self.block_stamina > 0.3
            and self.state_machine.current_state_name not in (
                PlayerState.WALL_SLIDE, PlayerState.HURT, PlayerState.DASH, PlayerState.STAGGER
            )
        )

    def _can_attack_interrupt(self) -> bool:
        """Check if the player can currently interrupt to attack."""
        return self.combat.is_attacking and self.can_attack()

    def _setup_interrupts(self) -> None:
        """Register player-specific state machine interrupts."""
        sm = self.state_machine
        sm.add_interrupt(
            PlayerState.HURT,
            lambda: self.combat.is_hurt,
            priority=100,
        )
        sm.add_interrupt(
            PlayerState.DASH,
            self._can_dash,
            priority=80,
        )
        sm.add_interrupt(
            PlayerState.BLOCK,
            self._can_block,
            priority=60,
        )
        sm.add_interrupt(
            PlayerState.ATTACK,
            self._can_attack_interrupt,
            priority=40,
        )

    @property
    def is_blocking(self) -> bool:
        """Return True if the player is currently blocking."""
        return self.state_machine.current_state_name == PlayerState.BLOCK

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

        self.face_movement()

        if im.jump_just_pressed:
            self.jump_buffer_timer = self.jump_buffer_duration

        if im.dash_just_pressed:
            self._dash_requested = (
                self.dash_charges > 0 and self.dash_penalty_timer <= 0
            )

        if im.reset_just_pressed:
            self.reset_position()

    def _handle_attack_input(self) -> None:
        """Process attack input with support for charge attacks.

        Chargeable attacks (heavy_attack) use a hold-to-charge, release-to-fire
        flow. Non-chargeable attacks fire immediately on press.

        While charging, entering a forbidden state (dash, hurt, etc.) cancels
        the charge. Releasing the charge button triggers the attack with a
        damage multiplier proportional to the hold duration.
        """
        im = self.input_manager

        if self.combat.charging.is_charging:
            if not self.can_attack():
                self.combat.charging.cancel()
                return
            if im.attack2_just_released:
                self.combat.release_charge()
            return

        if not self.can_attack():
            return

        if im.attack1_just_pressed:
            attack_name = "light_attack" if self.on_surface["floor"] else "air_attack"
            self.combat.start_attack(attack_name)
        elif im.attack2_just_pressed:
            if not self.combat.start_charge("heavy_attack"):
                self.combat.start_attack("heavy_attack")
        elif im.attack3_just_pressed:
            self.combat.start_attack("uppercut")
        elif im.attack4_just_pressed:
            self.combat.start_attack("dash_attack")

    def _update_jump_timers(self, delta_time: float) -> None:
        """Update jump buffer and coyote timers."""
        if self.jump_buffer_timer > 0:
            self.jump_buffer_timer -= delta_time

        if self.on_surface["floor"]:
            self.coyote_timer = self.coyote_duration
        elif self.coyote_timer > 0:
            self.coyote_timer -= delta_time

    def _update_block_stamina(self, delta_time: float) -> None:
        """Update block cooldown and stamina regeneration."""
        if self.block_cooldown_timer > 0:
            self.block_cooldown_timer -= delta_time

        if self.state_machine.current_state_name != PlayerState.BLOCK:
            if self.block_stamina < self.max_block_stamina:
                self.block_stamina += delta_time * 0.5
                self.block_stamina = min(
                    self.block_stamina, self.max_block_stamina)

    def _update_dash_recharge(self, delta_time: float) -> None:
        """Update dash penalty and recharge timers."""
        if self.dash_penalty_timer > 0:
            self.dash_penalty_timer -= delta_time
        else:
            if self.dash_charges < self.max_dash_charges:
                self.dash_recharge_timer -= delta_time
                if self.dash_recharge_timer <= 0:
                    self.dash_charges += 1
                    self.dash_recharge_timer = Physics.DASH_RECHARGE_TIME

    def update_timers(self, delta_time: float) -> None:
        """Update all player-specific timers."""
        self._update_jump_timers(delta_time)
        self._update_block_stamina(delta_time)
        self._update_dash_recharge(delta_time)

    def _pre_update(self, delta_time: float) -> None:
        """Process input and timers before combat and state machine updates."""
        self.get_input()
        self._handle_attack_input()
        self.update_timers(delta_time)

    def _post_update(self, delta_time: float) -> None:
        """Clear consumed inputs after state machine and physics updates."""
        if self.state_machine.current_state_name == PlayerState.DASH:
            self._dash_requested = False

    def handle_jump(self) -> None:
        """Process jump input with coyote time, wall jumps, and midair jumps."""
        resolve_jump(self)

    def _on_reset(self) -> None:
        """Full reset of all player-specific state."""
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
        self.hitbox.width = self._original_hitbox_width

    def respawn(self) -> None:
        """Alias for reset_position, used after death."""
        self.reset_position()

    def _apply_block_damage_reaction(
        self,
        amount: float,
        knockback: KnockbackConfig | None,
        source_center_x: float | None,
    ) -> DamageResult:
        """Handle damage while blocking: consume stamina, reduce knockback, and apply reduced push.

        Parameters
        ----------
        amount : float
            Raw damage amount used for stamina calculation.
        knockback : KnockbackConfig | None
            Original knockback configuration.
        source_center_x : float | None
            X-coordinate of the damage source.

        Returns
        -------
        DamageResult
            A dataclass detailing the outcome of the blocked damage.
        """
        _kb = knockback if knockback is not None else KnockbackConfig()
        self.block_stamina -= amount * CombatSettings.BLOCK_STAMINA_COST_RATIO
        if self.block_stamina < 0:
            self.block_stamina = 0.0

        direction = compute_knockback_direction(
            self.hitbox.centerx, source_center_x, self.facing_right
        )

        if _kb.mode == "fixed":
            self.velocity.x = _kb.power[0] * \
                CombatSettings.BLOCK_KNOCKBACK_FACTOR
        else:
            self.velocity.x = _kb.power[0] * \
                CombatSettings.BLOCK_KNOCKBACK_FACTOR * direction

        return DamageResult(blocked=True)

    def _can_receive_damage(self) -> bool:
        """Check if the player can receive damage, accounting for blocking."""
        return super()._can_receive_damage() and not self.is_blocking

    def receive_damage(
        self,
        amount: float,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
    ) -> DamageResult:
        """Override to add blocking logic and reduced hurt duration.

        If blocking, stamina is consumed and knockback is reduced; no health lost.
        Otherwise, delegate to the base implementation and reduce hurt duration.

        Parameters
        ----------
        amount : float
            Hit points to subtract.
        source_center_x : float | None
            X centre of the damage source for knockback direction.
        knockback : KnockbackConfig | None
            Knockback impulse configuration.
        interrupt : bool
            Whether the hit interrupts the entity's current action.

        Returns
        -------
        DamageResult
            A dataclass detailing the outcome of the damage application.
        """
        if not self._can_receive_damage():
            return DamageResult()

        if self.is_blocking:
            return self._apply_block_damage_reaction(amount, knockback, source_center_x)

        result = super().receive_damage(amount, source_center_x, knockback, interrupt)

        if interrupt and hasattr(self.combat, "hurt_timer") and self.combat.hurt_timer > 0:
            self.combat.hurt_timer = min(
                self.combat.hurt_timer,
                CombatSettings.PLAYER_HURT_DURATION,
            )

        return result
