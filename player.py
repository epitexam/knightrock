import math
from typing import Any, Iterable, Sequence

import pygame
from pygame.joystick import Joystick, JoystickType
from pygame.sprite import Group

from colors import Colors
from combat import AttackPhase, AttackSequence, CombatComponent
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

        self.combat.add_attack(
            "ground_combo",
            AttackSequence(
                phases=[
                    AttackPhase(
                        size=(38.0, 22.0), offset=(22.0, -2.0), damage=7, duration=0.10
                    ),
                    AttackPhase(
                        size=(46.0, 26.0), offset=(28.0, -6.0), damage=13, duration=0.16
                    ),
                ],
                cooldown=0.65,
                lock_direction=True,
            ),
        )

        self.combat.add_attack(
            "heavy_smash",
            AttackSequence(
                phases=[
                    AttackPhase(
                        size=(55.0, 42.0),
                        offset=(34.0, -26.0),
                        damage=20,
                        duration=0.25,
                    ),
                    AttackPhase(
                        size=(68.0, 16.0), offset=(28.0, 8.0), damage=8, duration=0.15
                    ),
                ],
                cooldown=1.3,
                lock_direction=True,
            ),
        )

        self.combat.add_attack(
            "uppercut",
            AttackSequence(
                phases=[
                    AttackPhase(
                        size=(36.0, 20.0), offset=(22.0, 2.0), damage=6, duration=0.08
                    ),
                    AttackPhase(
                        size=(30.0, 52.0),
                        offset=(16.0, -32.0),
                        damage=15,
                        duration=0.20,
                    ),
                ],
                cooldown=0.9,
                lock_direction=True,
            ),
        )

        self.combat.add_attack(
            "dash_strike",
            AttackSequence(
                phases=[
                    AttackPhase(
                        size=(58.0, 20.0), offset=(36.0, -8.0), damage=14, duration=0.14
                    ),
                ],
                cooldown=0.7,
                lock_direction=True,
            ),
        )

        self.combat.add_attack(
            "air_combo",
            AttackSequence(
                phases=[
                    AttackPhase(
                        size=(50.0, 26.0), offset=(28.0, -4.0), damage=9, duration=0.13
                    ),
                    AttackPhase(
                        size=(40.0, 34.0), offset=(20.0, 14.0), damage=14, duration=0.17
                    ),
                ],
                cooldown=0.95,
                lock_direction=False,
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
            lambda: (
                self.combat.is_attacking
                and sm.current_state_name not in ("wall_slide", "block", "hurt", "dash")
            ),
            priority=40,
        )

        self._key_prev: dict[int, bool] = {}
        self._joystick: JoystickType | None = (
            Joystick(0) if pygame.joystick.get_count() > 0 else None
        )
        self._button_prev: dict[int, bool] = {}
        self._trigger_prev: dict[int, bool] = {}

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

    @staticmethod
    def _apply_deadzone(value: float, deadzone: float) -> float:
        if abs(value) < deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - deadzone) / (1.0 - deadzone)

    def get_input(self) -> None:
        """Gathers and processes keyboard and controller inputs."""
        keys = pygame.key.get_pressed()
        joy = self._joystick
        _DZ = 0.2

        raw_joy_x = joy.get_axis(0) if joy else 0.0
        hat_x = joy.get_hat(0)[0] if joy else 0
        analog = self._apply_deadzone(raw_joy_x, _DZ) if joy else 0.0
        if analog == 0.0 and hat_x != 0:
            analog = float(hat_x)

        kb_axis = float(bool(keys[pygame.K_RIGHT])) - float(bool(keys[pygame.K_LEFT]))
        self.move_axis = kb_axis if kb_axis != 0.0 else analog

        self.left_held = self.move_axis < -0.1
        self.right_held = self.move_axis > 0.1

        jb: dict[int, bool] = {}
        jp: dict[int, bool] = {}
        lt_just = False
        if joy:
            for btn in (0, 1, 2, 3, 4, 5, 7):
                cur = bool(joy.get_button(btn))
                jb[btn] = cur
                jp[btn] = cur and not self._button_prev.get(btn, False)
                self._button_prev[btn] = cur
            lt_cur = joy.get_axis(2) > 0.5
            lt_just = lt_cur and not self._trigger_prev.get(2, False)
            self._trigger_prev[2] = lt_cur

        self.block_held = bool(keys[pygame.K_q]) or jb.get(4, False)

        if self.move_axis > 0.1:
            self.facing_right = True
        elif self.move_axis < -0.1:
            self.facing_right = False

        if self._is_key_pressed_once(pygame.K_SPACE, keys) or jp.get(0, False):
            self.jump_buffer_timer = self.jump_buffer_duration

        if self._is_key_pressed_once(pygame.K_LSHIFT, keys) or lt_just:
            if self.dash_charges > 0 and self.dash_penalty_timer <= 0:
                self._dash_requested = True
            else:
                self._dash_requested = False

        if self.state_machine is not None:
            current_state = self.state_machine.current_state_name
            can_attack = current_state not in ("wall_slide", "block", "hurt")
        else:
            can_attack = True

        if can_attack:
            if self._is_key_pressed_once(pygame.K_a, keys) or jp.get(1, False):
                attack = "air_combo" if not self.on_surface["floor"] else "ground_combo"
                self.combat.start_attack(attack, self.facing_right)

            elif self._is_key_pressed_once(pygame.K_s, keys) or jp.get(2, False):
                self.combat.start_attack("heavy_smash", self.facing_right)

            elif self._is_key_pressed_once(pygame.K_d, keys) or jp.get(3, False):
                self.combat.start_attack("uppercut", self.facing_right)

            elif self._is_key_pressed_once(pygame.K_f, keys) or jp.get(5, False):
                self.combat.start_attack("dash_strike", self.facing_right)

        if self._is_key_pressed_once(pygame.K_r, keys) or jp.get(7, False):
            self.reset_position()

    _dash_requested: bool = False

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

    def update(self, delta_time: float) -> None:
        """Core update cycle invoked each frame."""
        super().update(delta_time)
        self.get_input()
        self.update_timers(delta_time)
        self.combat.update(delta_time, self.facing_right)
        if self.state_machine is not None:
            self.state_machine.update(delta_time)
        self.move(delta_time)
