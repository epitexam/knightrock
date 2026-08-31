"""Player entity with full state machine, input reading, and combat mechanics."""

import math
from collections.abc import Iterable, Sequence
from enum import Enum
from typing import Any

import pygame
from pygame.sprite import Group

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.knockback import KnockbackConfig
from src.combat.combatant_protocol import DamageResult
from src.core.colors import Colors
from src.core.input.input_manager import InputManager
from src.core.settings import Combat as CombatSettings
from src.core.settings import Physics
from src.entities.entity import Entity, compute_knockback_direction
from src.entities.player_config import PlayerConfig
from src.entities.player_controllers import (
    BlockController,
    DashController,
    JumpController,
)
from src.physics import resolve_jump
from src.states.player_states import (
    PlayerAttackState,
    PlayerBlockState,
    PlayerChargeState,
    PlayerDashState,
    PlayerFallState,
    PlayerHurtState,
    PlayerIdleState,
    PlayerJumpState,
    PlayerKnockbackState,
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
    CHARGE = "charge"
    KNOCKBACK = "knockback"


ATTACK_FORBIDDEN_STATES = {
    PlayerState.WALL_SLIDE,
    PlayerState.BLOCK,
    PlayerState.HURT,
    PlayerState.DASH,
    PlayerState.STAGGER,
    PlayerState.KNOCKBACK,
}
"""Set of states where initiating an attack is forbidden."""


DEFAULT_PLAYER_CONFIG = PlayerConfig(
    size=(48.0, 56.0),
    color=Colors.pink,
    health=100.0,
    max_health=100.0,
    hitbox_inflate=(-8.0, 0.0),
    speed=Physics.PLAYER_SPEED,
    floor_control=Physics.FLOOR_CONTROL,
    air_control=Physics.AIR_CONTROL,
    jump_height=Physics.JUMP_FORCE,
    wall_jump_height=Physics.JUMP_FORCE * 0.90 * 1.15,
    wall_jump_push_multiplier=1.3,
    wall_jump_lock_duration=0.18,
    wall_jump_min_lock=0.08,
    wall_slide_speed=Physics.WALL_SLIDE_SPEED,
    max_midair_jumps=1,
    max_wall_jumps=math.inf,
    coyote_duration=Physics.COYOTE_DURATION,
    jump_buffer_duration=Physics.JUMP_BUFFER_DURATION,
    max_block_stamina=Physics.MAX_BLOCK_STAMINA,
    block_cooldown_normal=CombatSettings.BLOCK_COOLDOWN_NORMAL,
    block_cooldown_broken=CombatSettings.BLOCK_COOLDOWN_BROKEN,
    max_dash_charges=Physics.DASH_MAX_CHARGES,
    dash_speed=Physics.DASH_SPEED,
    dash_duration=Physics.DASH_DURATION,
    dash_friction=Physics.DASH_FRICTION,
    dash_penalty_duration=Physics.DASH_PENALTY_TIME,
    dash_recharge_time=Physics.DASH_RECHARGE_TIME,
    dash_gravity_mult=Physics.DASH_GRAVITY_MULT,
    hurt_duration=CombatSettings.PLAYER_HURT_DURATION,
    invincibility_duration=CombatSettings.INVINCIBILITY_DURATION,
    faction="player",
)


class Player(Entity):
    """Playable character with full state machine, input reading, and combat.

    Extends Entity with movement, jumping, dashing, blocking, and attacks.
    Utilizes the enhanced StateMachine with Input Buffering and State Tags.

    Attributes
    ----------
    input_manager : InputManager
        Source of player input.
    speed : float
        Base movement speed.
    floor_control : float
        Horizontal control when on the ground.
    air_control : float
        Horizontal control when airborne.
    jump : JumpController
        Owns jump resources: buffer, coyote time, wall lock, and jump stocks.
    block : BlockController
        Owns block resources: stamina pool and post-block cooldown.
    dash : DashController
        Owns dash resources: charges, recharge, penalty, and squished hitbox.
    """

    input_manager: InputManager
    speed: float
    floor_control: float
    air_control: float

    jump: JumpController
    block: BlockController
    dash: DashController

    moving_platforms: Iterable[Any]

    _space_held: bool
    _left_held: bool
    _right_held: bool
    _block_held: bool

    def __init__(
        self,
        pos: tuple[float, float] | pygame.math.Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        moving_platforms: Iterable[Any],
        input_manager: InputManager,
        config: PlayerConfig | None = None,
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
        config : PlayerConfig | None
            Optional player configuration. Uses DEFAULT_PLAYER_CONFIG if not provided.
        """
        config = config or DEFAULT_PLAYER_CONFIG

        attacks = None
        if hasattr(config, 'attacks') and config.attacks:
            attacks = dict(config.attacks)
        elif PLAYER_ATTACKS:
            attacks = PLAYER_ATTACKS

        super().__init__(
            pos,
            config.size,
            config.color,
            groups,
            collision_sprites,
            hitbox_inflate=config.hitbox_inflate,
            hurtbox_inflate=config.hurtbox_inflate,
            health=config.health,
            max_health=config.max_health,
            faction=config.faction,
            spawn_pos=pos,
            attacks=attacks,
            hurt_duration=config.hurt_duration,
            invincibility_duration=config.invincibility_duration,
        )

        self.speed = config.speed
        self.floor_control = config.floor_control
        self.air_control = config.air_control

        self.jump = JumpController(config)
        self.block = BlockController(config)
        self.dash = DashController(
            config, original_hitbox_width=self.hitbox.width
        )

        self.moving_platforms = moving_platforms

        self._buffered_attack_name: str | None = None

        self._space_held = False
        self._left_held = False
        self._right_held = False
        self._block_held = False

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
        self.state_machine.add_state(
            PlayerState.CHARGE, PlayerChargeState(self))
        self.state_machine.add_state(PlayerState.BLOCK, PlayerBlockState(self))
        self.state_machine.add_state(PlayerState.HURT, PlayerHurtState(self))
        self.state_machine.add_state(
            PlayerState.KNOCKBACK, PlayerKnockbackState(self))
        self.state_machine.add_state(PlayerState.DASH, PlayerDashState(self))
        self.state_machine.add_state(
            PlayerState.STAGGER, PlayerStaggerState(self))
        self.state_machine.set_initial_state(PlayerState.IDLE)
        self._setup_interrupts()

    def _can_dash(self) -> bool:
        """Check if the player can currently interrupt to dash."""
        return (
            self.dash.can_use()
            and self.state_machine.current_state_name not in (
                PlayerState.DASH, PlayerState.HURT, PlayerState.KNOCKBACK, PlayerState.STAGGER
            )
        )

    def _can_block(self) -> bool:
        """Check if the player can currently interrupt to block."""
        return (
            self.on_surface["floor"]
            and self.block_held
            and self.block.can_use()
            and self.state_machine.current_state_name not in (
                PlayerState.WALL_SLIDE, PlayerState.HURT, PlayerState.KNOCKBACK, PlayerState.DASH, PlayerState.STAGGER
            )
        )

    def _can_attack_interrupt(self) -> bool:
        """Check if the player can currently interrupt to attack."""
        return self.combat.is_attacking and self.can_attack()

    def _setup_interrupts(self) -> None:
        """Register player-specific state machine interrupts."""
        super()._setup_interrupts()
        sm = self.state_machine
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

    @property
    def space_held(self) -> bool:
        """Whether space is currently held."""
        return self._space_held

    @space_held.setter
    def space_held(self, value: bool) -> None:
        """Set space held state."""
        self._space_held = value

    @property
    def left_held(self) -> bool:
        """Whether left movement is currently held."""
        return self._left_held

    @left_held.setter
    def left_held(self, value: bool) -> None:
        """Set left held state."""
        self._left_held = value

    @property
    def right_held(self) -> bool:
        """Whether right movement is currently held."""
        return self._right_held

    @right_held.setter
    def right_held(self, value: bool) -> None:
        """Set right held state."""
        self._right_held = value

    @property
    def block_held(self) -> bool:
        """Whether block is currently held."""
        return self._block_held

    @block_held.setter
    def block_held(self, value: bool) -> None:
        """Set block held state."""
        self._block_held = value

    # ------------------------------------------------------------------
    # Flat delegation to the jump controller. resolve_jump (physics
    # protocols) and the debug UI read/mutate these on the entity.
    # ------------------------------------------------------------------
    @property
    def jump_buffer_timer(self) -> float:
        """Flat view of :attr:`JumpController.jump_buffer_timer`."""
        return self.jump.jump_buffer_timer

    @jump_buffer_timer.setter
    def jump_buffer_timer(self, value: float) -> None:
        self.jump.jump_buffer_timer = value

    @property
    def coyote_timer(self) -> float:
        """Flat view of :attr:`JumpController.coyote_timer`."""
        return self.jump.coyote_timer

    @coyote_timer.setter
    def coyote_timer(self, value: float) -> None:
        self.jump.coyote_timer = value

    @property
    def wall_jump_lock_timer(self) -> float:
        """Flat view of :attr:`JumpController.wall_jump_lock_timer`."""
        return self.jump.wall_jump_lock_timer

    @wall_jump_lock_timer.setter
    def wall_jump_lock_timer(self, value: float) -> None:
        self.jump.wall_jump_lock_timer = value

    @property
    def midair_jumps_left(self) -> int:
        """Flat view of :attr:`JumpController.midair_jumps_left`."""
        return self.jump.midair_jumps_left

    @midair_jumps_left.setter
    def midair_jumps_left(self, value: int) -> None:
        self.jump.midair_jumps_left = value

    @property
    def wall_jumps_left(self) -> int | float:
        """Flat view of :attr:`JumpController.wall_jumps_left`."""
        return self.jump.wall_jumps_left

    @wall_jumps_left.setter
    def wall_jumps_left(self, value: int | float) -> None:
        self.jump.wall_jumps_left = value

    @property
    def jump_height(self) -> float:
        """Flat view of :attr:`JumpController.jump_height`."""
        return self.jump.jump_height

    @property
    def wall_jump_height(self) -> float:
        """Flat view of :attr:`JumpController.wall_jump_height`."""
        return self.jump.wall_jump_height

    @property
    def wall_jump_push_multiplier(self) -> float:
        """Flat view of :attr:`JumpController.wall_jump_push_multiplier`."""
        return self.jump.wall_jump_push_multiplier

    @property
    def wall_jump_lock_duration(self) -> float:
        """Flat view of :attr:`JumpController.wall_jump_lock_duration`."""
        return self.jump.wall_jump_lock_duration

    @property
    def wall_jump_min_lock(self) -> float:
        """Flat view of :attr:`JumpController.wall_jump_min_lock`."""
        return self.jump.wall_jump_min_lock

    # ------------------------------------------------------------------
    # Flat delegation to the block controller (debug UI, hit resolver).
    # ------------------------------------------------------------------
    @property
    def block_stamina(self) -> float:
        """Flat view of :attr:`BlockController.block_stamina`."""
        return self.block.block_stamina

    @block_stamina.setter
    def block_stamina(self, value: float) -> None:
        self.block.block_stamina = value

    @property
    def max_block_stamina(self) -> float:
        """Flat view of :attr:`BlockController.max_block_stamina`."""
        return self.block.max_block_stamina

    @property
    def block_cooldown_timer(self) -> float:
        """Flat view of :attr:`BlockController.block_cooldown_timer`."""
        return self.block.block_cooldown_timer

    @block_cooldown_timer.setter
    def block_cooldown_timer(self, value: float) -> None:
        self.block.block_cooldown_timer = value

    # ------------------------------------------------------------------
    # Flat delegation to the dash controller (debug UI).
    # ------------------------------------------------------------------
    @property
    def dash_charges(self) -> int:
        """Flat view of :attr:`DashController.charges`."""
        return self.dash.charges

    @dash_charges.setter
    def dash_charges(self, value: int) -> None:
        self.dash.charges = value

    @property
    def max_dash_charges(self) -> int:
        """Flat view of :attr:`DashController.max_charges`."""
        return self.dash.max_charges

    @property
    def dash_recharge_timer(self) -> float:
        """Flat view of :attr:`DashController.recharge_timer`."""
        return self.dash.recharge_timer

    @dash_recharge_timer.setter
    def dash_recharge_timer(self, value: float) -> None:
        self.dash.recharge_timer = value

    @property
    def dash_penalty_timer(self) -> float:
        """Flat view of :attr:`DashController.penalty_timer`."""
        return self.dash.penalty_timer

    @dash_penalty_timer.setter
    def dash_penalty_timer(self, value: float) -> None:
        self.dash.penalty_timer = value

    @property
    def dash_requested(self) -> bool:
        """Flat view of :attr:`DashController.requested`."""
        return self.dash.requested

    @dash_requested.setter
    def dash_requested(self, value: bool) -> None:
        self.dash.requested = value

    @property
    def dash_speed(self) -> float:
        """Flat view of :attr:`DashController.speed`."""
        return self.dash.speed

    @property
    def dash_duration(self) -> float:
        """Flat view of :attr:`DashController.duration`."""
        return self.dash.duration

    @property
    def dash_friction(self) -> float:
        """Flat view of :attr:`DashController.friction`."""
        return self.dash.friction

    def can_attack(self) -> bool:
        """Return True if an attack can be started from the current state."""
        return self.state_machine.current_state_name not in ATTACK_FORBIDDEN_STATES

    def is_wall_sliding(self) -> bool:
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
        self.jump.restore_ground_jumps()

    def _on_wall_contact(self) -> None:
        """Reset midair jumps when touching a wall."""
        self.jump.restore_midair_jumps()

    def get_input(self) -> None:
        """Read all input and update facing direction and buffers."""
        im = self.input_manager
        self.move_axis = im.move_axis
        self.left_held = im.left_held
        self.right_held = im.right_held
        self.block_held = im.block_held

        self.face_movement()

        if im.jump_just_pressed:
            self.jump.buffer_press()

        if im.dash_just_pressed:
            self.dash.request()

        if im.reset_just_pressed:
            self.reset_position()

    def _handle_attack_input(self) -> None:
        """Process attack input with support for charge attacks, input buffering, and combos."""
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

        if im.special_attack_just_pressed:
            self.combat.start_attack("special_attack")
            return

        if im.attack1_just_pressed:
            attack_name = "light_attack" if self.on_surface["floor"] else "air_attack"
            if not self.combat.start_attack(attack_name):
                self._buffered_attack_name = attack_name
                self.state_machine.buffer_input("attack", window=0.2)
        elif im.attack2_just_pressed:
            if self.combat.start_charge("heavy_attack"):
                self.state_machine.change_state(PlayerState.CHARGE, force=True)
            else:
                self.combat.start_attack("heavy_attack")
        elif im.attack3_just_pressed:
            self.combat.start_attack("uppercut")
        elif im.attack4_just_pressed:
            self.combat.start_attack("dash_attack")

    def update_timers(self, delta_time: float) -> None:
        """Update every controller's timers (buffer, coyote, stamina, dash)."""
        is_blocking = (
            self.state_machine.current_state_name == PlayerState.BLOCK
        )
        self.jump.update(delta_time, self.on_surface["floor"])
        self.block.update(delta_time, is_blocking)
        self.dash.update(delta_time)

    def _pre_update(self, delta_time: float) -> None:
        """Process input and timers before combat and state machine updates."""
        self.get_input()
        self._handle_attack_input()
        self.update_timers(delta_time)

    def _post_update(self, delta_time: float) -> None:
        """Clear consumed inputs after state machine and physics updates."""
        if self.state_machine.current_state_name == PlayerState.DASH:
            self.dash.cancel_request()

    def handle_jump(self) -> None:
        """Process jump input with coyote time, wall jumps, and midair jumps."""
        resolve_jump(self)

    def _on_reset(self) -> None:
        """Full reset of all player-specific state."""
        self.jump.reset()
        self.block.reset()
        self.dash.reset()
        self.move_axis = 0.0
        self._buffered_attack_name = None
        self.hitbox.width = self.dash.original_hitbox_width

        self._space_held = False
        self._left_held = False
        self._right_held = False
        self._block_held = False

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
        _kb = (
            knockback
            if knockback is not None
            else KnockbackConfig(power=(0.0, 0.0))
        )
        self.block.consume(amount * CombatSettings.BLOCK_STAMINA_COST_RATIO)

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
        """Check immunity/death; blocking is resolved as an explicit outcome."""
        return super()._can_receive_damage()

    def receive_damage(
        self,
        amount: float,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
    ) -> DamageResult:
        """Override to add blocking logic and cap hurt duration.

        If blocking, stamina is consumed and knockback is reduced; no health lost.
        Otherwise, the base entity logic is applied and the hurt timer is capped.

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
            return self._apply_block_damage_reaction(
                amount, knockback, source_center_x
            )

        result = super().receive_damage(amount, source_center_x, knockback, interrupt)

        if interrupt and hasattr(self.combat, "hurt_timer") and self.combat.hurt_timer > 0:
            self.combat.hurt_timer = min(
                self.combat.hurt_timer,
                CombatSettings.PLAYER_HURT_DURATION,
            )

        return result

