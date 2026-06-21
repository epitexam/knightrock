from typing import Any, Iterable, Sequence

import pygame
from pygame.sprite import Group

from colors import Colors
from combat import AttackData, CombatComponent
from entity import Entity
from player_states import (
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
from settings import Physics
from state_machine import StateMachine


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
    wall_jump_boost: float
    wall_slide_speed: float
    max_midair_jumps: int
    midair_jumps_left: int
    max_wall_jumps: int
    wall_jumps_left: int
    space_held: bool
    left_held: bool
    right_held: bool
    block_held: bool
    coyote_timer: float
    coyote_duration: float
    jump_buffer_timer: float
    jump_buffer_duration: float
    wall_jump_timer: float
    wall_jump_duration: float
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

    def __init__(
        self,
        pos: tuple[float, float] | pygame.math.Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        moving_platforms: Iterable[Any],
    ) -> None:
        super().__init__(
            pos,
            (48.0, 56.0),
            Colors.green,
            groups,
            collision_sprites,
            hitbox_inflate=(-8.0, 0.0),
        )

        self.speed = float(Physics.PLAYER_SPEED)
        self.floor_control = 25.0
        self.air_control = 12.0

        self.jump_height = float(Physics.JUMP_FORCE)
        self.wall_jump_height = float(Physics.JUMP_FORCE) * 0.90
        self.wall_jump_boost = 1.6
        self.wall_slide_speed = 100.0

        self.max_midair_jumps = 1
        self.midair_jumps_left = self.max_midair_jumps
        self.max_wall_jumps = 9999
        self.wall_jumps_left = self.max_wall_jumps

        self.space_held = False
        self.left_held = False
        self.right_held = False
        self.block_held = False

        self.coyote_timer = 0.0
        self.coyote_duration = 0.12

        self.jump_buffer_timer = 0.0
        self.jump_buffer_duration = 0.10

        self.wall_jump_timer = 0.0
        self.wall_jump_duration = 0.15

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

        self.combat.add_attack(
            "light_punch",
            AttackData(
                size=(45.0, 20.0),
                offset=(30.0, -10.0),
                damage=10,
                duration=0.15,
                cooldown=0.3,
            ),
        )

        self.combat.add_attack(
            "heavy_smash",
            AttackData(
                size=(60.0, 40.0),
                offset=(40.0, -5.0),
                damage=25,
                duration=0.4,
                cooldown=1.2,
            ),
        )

        self.combat.add_attack(
            "uppercut",
            AttackData(
                size=(30.0, 60.0),
                offset=(20.0, -40.0),
                damage=15,
                duration=0.25,
                cooldown=0.8,
            ),
        )

        self.combat.add_attack(
            "dash_strike",
            AttackData(
                size=(80.0, 15.0),
                offset=(50.0, -15.0),
                damage=12,
                duration=0.1,
                cooldown=0.6,
            ),
        )

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

        self._key_prev: dict[int, bool] = {}

    def _is_key_pressed_once(self, key: int, keys: pygame.key.ScancodeWrapper) -> bool:
        """Returns True if the key was just pressed (transition from not pressed to pressed)."""
        current = bool(keys[key])
        previous = self._key_prev.get(key, False)
        self._key_prev[key] = current
        return current and not previous

    def _is_key_held(self, key: int, keys: pygame.key.ScancodeWrapper) -> bool:
        """Returns True if the key is currently held down."""
        current = bool(keys[key])
        self._key_prev[key] = current
        return current

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
        """Gathers and processes keyboard inputs."""
        keys = pygame.key.get_pressed()

        self.left_held = bool(keys[pygame.K_LEFT])
        self.right_held = bool(keys[pygame.K_RIGHT])

        self.block_held = bool(keys[pygame.K_q])

        if self.right_held and not self.left_held:
            self.facing_right = True
        elif self.left_held and not self.right_held:
            self.facing_right = False

        if self._is_key_pressed_once(pygame.K_SPACE, keys):
            self.jump_buffer_timer = self.jump_buffer_duration

        if self._is_key_pressed_once(pygame.K_LSHIFT, keys):
            if (
                self.state_machine is not None
                and self.dash_charges > 0
                and self.state_machine.current_state_name != "dash"
            ):
                self._dash_requested = True

        if self.state_machine is not None:
            current_state = self.state_machine.current_state_name
            can_attack = current_state not in ("wall_slide", "block", "hurt")
        else:
            can_attack = True

        if can_attack:
            if self._is_key_pressed_once(pygame.K_a, keys):
                self.combat.start_attack("light_punch", self.facing_right)
            elif self._is_key_pressed_once(pygame.K_s, keys):
                self.combat.start_attack("heavy_smash", self.facing_right)
            elif self._is_key_pressed_once(pygame.K_d, keys):
                self.combat.start_attack("uppercut", self.facing_right)
            elif self._is_key_pressed_once(pygame.K_f, keys):
                self.combat.start_attack("dash_strike", self.facing_right)

        if self._is_key_pressed_once(pygame.K_r, keys):
            self.reset_position()

    _dash_requested: bool = False

    def update_timers(self, delta_time: float) -> None:
        """Decrements all game-feel buffers and timers."""
        if self.jump_buffer_timer > 0:
            self.jump_buffer_timer -= delta_time
        if self.wall_jump_timer > 0:
            self.wall_jump_timer -= delta_time

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
        if self.wall_jump_timer > 0:
            return

        target_speed: float = (int(self.right_held) - int(self.left_held)) * self.speed

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
        """
        Evaluates jump requests against buffered inputs and physics context.
        This method is now called from the state machine (e.g., PlayerJumpState),
        but kept for potential use or reference.
        """
        if self.jump_buffer_timer <= 0:
            return

        if self.coyote_timer > 0:
            self.velocity.y = -self.jump_height
            self.jump_buffer_timer = 0.0
            self.coyote_timer = 0.0

        elif (
            self.on_surface["left"] or self.on_surface["right"]
        ) and self.wall_jumps_left > 0:
            direction: float = 1.0 if self.on_surface["left"] else -1.0
            self.velocity.x = self.speed * self.wall_jump_boost * direction
            self.velocity.y = -self.wall_jump_height
            self.wall_jumps_left -= 1
            self.jump_buffer_timer = 0.0
            self.wall_jump_timer = self.wall_jump_duration

        elif self.midair_jumps_left > 0:
            self.velocity.y = -self.jump_height
            self.midair_jumps_left -= 1
            self.jump_buffer_timer = 0.0

    def move(self, delta_time: float) -> None:
        """
        Performs full physics resolution sequence including collisions.
        Horizontal movement is driven by the state machine.
        Gravity and sliding are now handled by Entity.apply_gravity.
        """
        self.apply_moving_platform(self.moving_platforms)

        self.hitbox.x += self.velocity.x * delta_time
        self.handle_collisions("horizontal")

        self.apply_gravity(delta_time)

        self.hitbox.y += self.velocity.y * delta_time
        self.handle_collisions("vertical")

        self.check_contact()

    def reset_position(self) -> None:
        """Resets player position and fully replenishes state variables."""
        super().reset_position()
        self.jump_buffer_timer = 0.0
        self.wall_jump_timer = 0.0
        self.coyote_timer = 0.0
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

    def update(self, delta_time: float) -> None:
        """Core update cycle invoked each frame."""
        super().update(delta_time)
        self.get_input()
        self.update_timers(delta_time)
        self.combat.update(delta_time, self.facing_right)

        assert self.state_machine is not None
        self.state_machine.update(delta_time)

        self.move(delta_time)
