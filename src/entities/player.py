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
from src.core.settings import Physics
from src.states.state_machine import StateMachine
from src.combat.attack_data import PLAYER_ATTACKS

ATTACK_FORBIDDEN_STATES = {"wall_slide", "block", "hurt", "dash"}


class Player(Entity):
    """
    Represents the playable character with precise, responsive platforming physics
    inspired by modern tight-control platformers like Celeste.
    """

    speed: float
    floor_control: float
    air_control: float
    jump_height: float
    wall_jump_height: float
    wall_slide_speed: float
    max_midair_jumps: int
    midair_jumps_left: int
    max_wall_jumps: int
    wall_jumps_left: int
    space_held: bool
    left_held: bool
    right_held: bool
    block_held: bool
    move_axis: float
    coyote_timer: float
    coyote_duration: float
    jump_buffer_timer: float
    jump_buffer_duration: float
    moving_platforms: Iterable[Any]
    _dash_duration_timer: float
    _original_hitbox_width: float

    max_block_stamina: float
    block_stamina: float
    block_cooldown_timer: float

    max_dash_charges: int
    dash_charges: int
    dash_recharge_timer: float
    dash_penalty_timer: float
    dash_speed: float
    dash_duration: float
    dash_friction: float
    dash_penalty_duration: float

    facing_right: bool
    combat: CombatComponent
    state_machine: StateMachine

    def __init__(
        self,
        pos: tuple[float, float] | pygame.math.Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        moving_platforms: Iterable[Any],
        input_manager: InputManager,
    ) -> None:
        super().__init__(
            pos,
            (48.0, 56.0),
            Colors.green,
            groups,
            collision_sprites,
            hitbox_inflate=(-8.0, 0.0),
            health=100.0,
            max_health=100.0,
        )

        self.speed = float(Physics.PLAYER_SPEED)
        self.floor_control = 25.0
        self.air_control = 12.0

        self.jump_height = float(Physics.JUMP_FORCE)
        self.wall_jump_height = float(Physics.JUMP_FORCE) * 0.90
        self.wall_slide_speed = 100.0

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
        self.coyote_duration = 0.12

        self.jump_buffer_timer = 0.0
        self.jump_buffer_duration = 0.10

        self.moving_platforms = moving_platforms

        self.max_block_stamina = 0.75
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

        self.combat = CombatComponent(self)
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

    def can_attack(self) -> bool:
        """Returns True if the current state allows starting an attack."""
        if self.state_machine is None:
            return False
        return self.state_machine.current_state_name not in ATTACK_FORBIDDEN_STATES

    def _is_wall_sliding(self) -> bool:
        """Checks if the player is actively pressing against a wall while falling."""
        on_left_wall: bool = self.on_surface["left"] and self.left_held
        on_right_wall: bool = self.on_surface["right"] and self.right_held
        return (
            not self.on_surface["floor"]
            and (on_left_wall or on_right_wall)
            and self.velocity.y > 0
        )

    def _on_floor_contact(self) -> None:
        """Resets jump resources upon touching the ground."""
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def _on_wall_contact(self) -> None:
        """Resets mid-air resources upon touching a wall."""
        self.midair_jumps_left = self.max_midair_jumps

    def get_input(self) -> None:
        """Gathers and processes keyboard and controller inputs via InputManager."""
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

        if self.can_attack():
            if im.attack1_just_pressed:
                attack = "air_combo" if not self.on_surface["floor"] else "ground_combo"
                self.combat.start_attack(attack, self.facing_right)
            elif im.attack2_just_pressed:
                self.combat.start_attack("heavy_smash", self.facing_right)
            elif im.attack3_just_pressed:
                self.combat.start_attack("uppercut", self.facing_right)
            elif im.attack4_just_pressed:
                self.combat.start_attack("dash_strike", self.facing_right)

        if im.reset_just_pressed:
            self.reset_position()

    def update_timers(self, delta_time: float) -> None:
        """Decrements all game-feel buffers and timers."""
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
        """Calculates and interpolates horizontal velocity based on context and inputs."""
        target_speed: float = self.move_axis * self.speed

        if self.combat.is_attacking and self.on_surface["floor"]:
            target_speed = 0.0

        if target_speed == 0 and abs(self.velocity.x) < 0.5:
            self.velocity.x = 0.0
            return

        control: float = (
            self.floor_control if self.on_surface["floor"] else self.air_control
        )
        self.velocity.x = pygame.math.lerp(
            self.velocity.x, target_speed, min(1.0, control * delta_time)
        )

        if abs(self.velocity.x) < 0.01:
            self.velocity.x = 0.0

    def handle_jump(self) -> None:
        """Evaluates jump requests against buffered inputs and physics context."""
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
        """Performs full physics resolution sequence including collisions (with sub-stepping)."""
        self.apply_moving_platform(self.moving_platforms)
        super().move(delta_time, apply_gravity=apply_gravity)

    def reset_position(self) -> None:
        """Resets player position and fully replenishes state variables."""
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
        """Override death behavior: reset position instead of removing."""
        self.is_dead = True

        self.reset_position()

        self.is_dead = False

    def update(self, delta_time: float) -> None:
        """Core update cycle invoked each frame."""
        super().update(delta_time)
        self.get_input()
        self.update_timers(delta_time)
        self.combat.update(delta_time, self.facing_right)
        if self.state_machine is not None:
            self.state_machine.update(delta_time)
        self.move(delta_time)
