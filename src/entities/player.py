import math
from typing import Any, Iterable, Sequence

import pygame
from pygame.sprite import Group

from src.core.colors import Colors
from src.combat.combat import CombatComponent
from src.entities.entity import Entity
from src.core.input_manager import InputManager
from src.states.player_states import (
    PlayerAttackState,
    PlayerBlockState,
    PlayerDashState,
    PlayerFallState,
    PlayerHurtState,
    PlayerIdleState,
    PlayerJumpState,
    PlayerRunState,
    PlayerWallSlideState,
)
from src.core.settings import Physics, Combat as CombatSettings
from src.states.state_machine import StateMachine
from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.attack_types import KnockbackConfig

ATTACK_FORBIDDEN_STATES = {"wall_slide", "block", "hurt", "dash"}


class Player(Entity):
    def __init__(
        self,
        pos: tuple[float, float] | pygame.math.Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        moving_platforms: Iterable[Any],
        input_manager: InputManager,
    ) -> None:
        combat = CombatComponent(self)

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
            combat=combat,
        )

        self.speed = float(Physics.PLAYER_SPEED)
        self.floor_control = Physics.FLOOR_CONTROL
        self.air_control = Physics.AIR_CONTROL

        self.jump_height = float(Physics.JUMP_FORCE)
        self.wall_jump_height = float(Physics.JUMP_FORCE) * 0.90
        self.wall_slide_speed = Physics.WALL_SLIDE_SPEED

        self.max_midair_jumps = 1
        self.midair_jumps_left = self.max_midair_jumps
        self.max_wall_jumps = 9999
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

        self.facing_right = True

        for name, sequence in PLAYER_ATTACKS.items():
            self.combat.add_attack(name, sequence)

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
                and sm.current_state_name not in ("dash", "hurt")
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
                and sm.current_state_name not in ("wall_slide", "hurt", "dash")
            ),
            priority=60,
        )
        sm.add_interrupt(
            "attack",
            lambda: (self.combat.is_attacking and self.can_attack()),
            priority=40,
        )

        self.input_manager = input_manager
        self._dash_requested = False

    @property
    def is_blocking(self) -> bool:
        if self.state_machine is None:
            return False
        return self.state_machine.current_state_name == "block"

    def can_attack(self) -> bool:
        if self.state_machine is None:
            return False
        return self.state_machine.current_state_name not in ATTACK_FORBIDDEN_STATES

    def _is_wall_sliding(self) -> bool:
        on_left_wall = self.on_surface["left"] and self.left_held
        on_right_wall = self.on_surface["right"] and self.right_held
        return (
            not self.on_surface["floor"]
            and (on_left_wall or on_right_wall)
            and self.velocity.y > 0
        )

    def _on_floor_contact(self) -> None:
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def _on_wall_contact(self) -> None:
        self.midair_jumps_left = self.max_midair_jumps

    def get_input(self) -> None:
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
        """Map input to attack selection based on context."""
        im = self.input_manager
        if not self.can_attack():
            return

        if im.attack1_just_pressed:
            attack = "air_combo" if not self.on_surface["floor"] else "ground_combo"
            self.combat.start_attack(attack, self.facing_right)
        elif im.attack2_just_pressed:
            self.combat.start_attack("heavy_smash", self.facing_right)
        elif im.attack3_just_pressed:
            self.combat.start_attack("uppercut", self.facing_right)
        elif im.attack4_just_pressed:
            self.combat.start_attack("dash_strike", self.facing_right)

    def update_timers(self, delta_time: float) -> None:
        if self.jump_buffer_timer > 0:
            self.jump_buffer_timer -= delta_time

        if self.on_surface["floor"]:
            self.coyote_timer = self.coyote_duration
        elif self.coyote_timer > 0:
            self.coyote_timer -= delta_time

        if self.block_cooldown_timer > 0:
            self.block_cooldown_timer -= delta_time

        if (
            self.state_machine is not None
            and self.state_machine.current_state_name != "block"
        ):
            if self.block_stamina < self.max_block_stamina:
                self.block_stamina += delta_time * 0.5
                self.block_stamina = min(self.block_stamina, self.max_block_stamina)

        if self.dash_penalty_timer > 0:
            self.dash_penalty_timer -= delta_time
        else:
            if self.dash_charges < self.max_dash_charges:
                self.dash_recharge_timer -= delta_time
                if self.dash_recharge_timer <= 0:
                    self.dash_charges += 1
                    self.dash_recharge_timer = Physics.DASH_RECHARGE_TIME

    def apply_horizontal_movement(self, delta_time: float) -> None:
        target_speed = self.move_axis * self.speed

        if self.combat.is_attacking and self.on_surface["floor"]:
            target_speed = 0.0

        if target_speed == 0 and abs(self.velocity.x) < 0.5:
            self.velocity.x = 0.0
            return

        control = self.floor_control if self.on_surface["floor"] else self.air_control
        self.velocity.x = pygame.math.lerp(
            self.velocity.x, target_speed, min(1.0, control * delta_time)
        )

        if abs(self.velocity.x) < 0.01:
            self.velocity.x = 0.0

    def handle_jump(self) -> None:
        if self.jump_buffer_timer <= 0:
            return

        if self.coyote_timer > 0:
            self.velocity.y = -self.jump_height
            self.jump_buffer_timer = 0.0
            self.coyote_timer = 0.0

        elif (
            self.on_surface["left"] or self.on_surface["right"]
        ) and self.wall_jumps_left > 0:
            self.velocity.y = -self.wall_jump_height
            self.wall_jumps_left -= 1
            self.jump_buffer_timer = 0.0

        elif self.midair_jumps_left > 0:
            self.velocity.y = -self.jump_height
            self.midair_jumps_left -= 1
            self.jump_buffer_timer = 0.0

    def move(self, delta_time: float, apply_gravity: bool = True) -> None:
        self.apply_moving_platform(self.moving_platforms)
        super().move(delta_time, apply_gravity=apply_gravity)

    def reset_position(self) -> None:
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
        self.hitbox.width = self._original_hitbox_width

        if self.combat.current_attack:
            self.combat.current_attack = None
            self.combat.attack_box = None

        self.health = self.max_health

    def die(self) -> None:
        """Mark player as dead without resetting position (respawn handled by Level)."""
        super().die()

    def respawn(self) -> None:
        """Respawn the player at spawn point."""
        self.is_dead = False
        self.reset_position()

    def receive_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None:
        if self.is_blocking:
            _kb = knockback if knockback is not None else KnockbackConfig()
            self.block_stamina -= amount * CombatSettings.BLOCK_STAMINA_COST_RATIO
            if _kb.mode == "fixed":
                self.velocity.x = _kb.power[0] * CombatSettings.BLOCK_KNOCKBACK_FACTOR
            elif source_center_x is not None:
                direction = 1.0 if self.hitbox.centerx >= source_center_x else -1.0
                self.velocity.x = (
                    _kb.power[0] * CombatSettings.BLOCK_KNOCKBACK_FACTOR * direction
                )
            return

        super().receive_damage(amount, source_center_x, knockback)

    def update(self, delta_time: float) -> None:
        if self.is_dead:
            return
        super().update(delta_time)
        self.get_input()
        self._handle_attack_input()
        self.update_timers(delta_time)
        self.combat.update(delta_time, self.facing_right)
        if self.state_machine is not None:
            self.state_machine.update(delta_time)
        self.move(delta_time)
