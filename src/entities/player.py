"""Player entity with full state machine, input reading, and combat mechanics."""

from collections.abc import Iterable, Sequence
from typing import Any, ClassVar

import pygame
from pygame.sprite import Group

from src.combat.attack_data import PLAYER_ATTACKS
from src.combat.combatant_protocol import DamageResult
from src.combat.knockback import NULL_KNOCKBACK, KnockbackConfig
from src.core.animation.animator import Animator
from src.core.asset_library import shared_library
from src.core.input.input_manager import InputManager
from src.core.settings import Combat as CombatSettings
from src.entities.controller_view import ControllerView
from src.entities.entity import Entity, compute_knockback_direction
from src.entities.player_animation import PLAYER_ANIMATIONS
from src.entities.player_config import DEFAULT_PLAYER_CONFIG, PlayerConfig
from src.entities.player_controllers import (
    BlockController,
    DashController,
    JumpController,
)
from src.entities.player_input import PlayerInputHandler
from src.physics import resolve_jump
from src.states.player_states import (
    ATTACK_FORBIDDEN_STATES,
    PlayerState,
    configure_player_state_machine,
)


class Player(ControllerView, Entity):
    """Playable character with full state machine, input reading, and combat.

    Extends Entity with movement, jumping, dashing, blocking, and attacks.
    Utilizes the enhanced StateMachine with Input Buffering and State Tags.

    The class is a thin aggregate (audit F1.1, Phase 2 #3): capability
    resources live in the ``jump``/``block``/``dash`` controllers, input
    reading lives in the ``input_handler``, and flat attribute access to
    controller fields is provided by :class:`ControllerView` instead of
    ~50 hand-written delegating properties.

    Attributes
    ----------
    input_manager : InputManager
        Source of player input.
    input_handler : PlayerInputHandler
        Reads the input manager each tick and drives abilities/attacks.
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
    input_handler: PlayerInputHandler

    moving_platforms: Iterable[Any]

    left_held: bool
    right_held: bool
    block_held: bool

    CONTROLLER_VIEWS: ClassVar[dict[str, tuple[str, str]]] = {
        # Jump controller (physics protocols JumpEntity/WallJumpLock, debug UI)
        "jump_buffer_timer": ("jump", "jump_buffer_timer"),
        "coyote_timer": ("jump", "coyote_timer"),
        "wall_jump_lock_timer": ("jump", "wall_jump_lock_timer"),
        "midair_jumps_left": ("jump", "midair_jumps_left"),
        "wall_jumps_left": ("jump", "wall_jumps_left"),
        "jump_height": ("jump", "jump_height"),
        "wall_jump_height": ("jump", "wall_jump_height"),
        "wall_jump_push_multiplier": ("jump", "wall_jump_push_multiplier"),
        "wall_jump_lock_duration": ("jump", "wall_jump_lock_duration"),
        "wall_jump_min_lock": ("jump", "wall_jump_min_lock"),
        # Block controller (debug UI, hit resolver)
        "block_stamina": ("block", "block_stamina"),
        "max_block_stamina": ("block", "max_block_stamina"),
        "block_cooldown_timer": ("block", "block_cooldown_timer"),
        # Dash controller (debug UI)
        "dash_charges": ("dash", "charges"),
        "max_dash_charges": ("dash", "max_charges"),
        "dash_recharge_timer": ("dash", "recharge_timer"),
        "dash_penalty_timer": ("dash", "penalty_timer"),
        "dash_requested": ("dash", "requested"),
        "dash_speed": ("dash", "speed"),
        "dash_duration": ("dash", "duration"),
        "dash_friction": ("dash", "friction"),
    }

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
        if hasattr(config, "attacks") and config.attacks:
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
        self.dash = DashController(config, original_hitbox_width=self.hitbox.width)

        self.moving_platforms = moving_platforms

        self.left_held = False
        self.right_held = False
        self.block_held = False

        self.input_manager = input_manager
        self.input_handler = PlayerInputHandler(self)

        self.animator = Animator(shared_library(), PLAYER_ANIMATIONS, default="idle")
        self._setup_state_machine()

    def _setup_state_machine(self) -> None:
        """Build the 12-state machine; states and interrupts live in player_states."""
        configure_player_state_machine(self)
        self._setup_interrupts()

    def _setup_interrupts(self) -> None:
        """Register the shared hurt interrupt (dash/block/attack in player_states)."""
        super()._setup_interrupts()

    @property
    def is_blocking(self) -> bool:
        """Return True if the player is currently blocking."""
        return self.state_machine.current_state_name == PlayerState.BLOCK

    @property
    def _buffered_attack_name(self) -> str | None:
        """Attack buffered when a start request was refused (combos)."""
        return self.input_handler.buffered_attack_name

    @_buffered_attack_name.setter
    def _buffered_attack_name(self, value: str | None) -> None:
        self.input_handler.buffered_attack_name = value

    def can_attack(self) -> bool:
        """Return True if an attack can be started from the current state."""
        return self.state_machine.current_state_name not in ATTACK_FORBIDDEN_STATES

    def is_wall_sliding(self) -> bool:
        """Return True when sliding down a wall."""
        on_left_wall = self.on_surface["left"] and self.left_held
        on_right_wall = self.on_surface["right"] and self.right_held
        return (
            not self.on_surface["floor"] and (on_left_wall or on_right_wall) and self.velocity.y > 0
        )

    def _on_floor_contact(self) -> None:
        """Reset midair and wall jumps when landing."""
        self.jump.restore_ground_jumps()

    def _on_wall_contact(self) -> None:
        """Reset midair jumps when touching a wall."""
        self.jump.restore_midair_jumps()

    def update_timers(self, delta_time: float) -> None:
        """Update every controller's timers (buffer, coyote, stamina, dash)."""
        is_blocking = self.state_machine.current_state_name == PlayerState.BLOCK
        self.jump.update(delta_time, self.on_surface["floor"])
        self.block.update(delta_time, is_blocking)
        self.dash.update(delta_time)

    def _animation_name(self) -> str | None:
        """Map the current player state to its sprite-sheet animation."""
        state: str | None = self.state_machine.current_state_name
        if state is None:
            return None
        if state == PlayerState.ATTACK:
            return "air_attack" if not self.on_surface["floor"] else "attack"
        if state in (PlayerState.HURT, PlayerState.KNOCKBACK, PlayerState.STAGGER):
            return "hit"
        mapping: dict[str, str] = {
            PlayerState.IDLE: "idle",
            PlayerState.RUN: "run",
            PlayerState.JUMP: "jump",
            PlayerState.FALL: "fall",
            PlayerState.WALL_SLIDE: "wall",
        }
        return mapping.get(state)

    def _pre_update(self, delta_time: float) -> None:
        """Process input and timers before combat and state machine updates."""
        self.input_handler.update()
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
        self.input_handler.buffered_attack_name = None
        self.hitbox.width = self.dash.original_hitbox_width

        self.left_held = False
        self.right_held = False
        self.block_held = False

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
        _kb = knockback if knockback is not None else NULL_KNOCKBACK
        self.block.consume(amount * CombatSettings.BLOCK_STAMINA_COST_RATIO)

        direction = compute_knockback_direction(
            self.hitbox.centerx, source_center_x, self.facing_right
        )

        if _kb.mode == "fixed":
            self.velocity.x = _kb.power[0] * CombatSettings.BLOCK_KNOCKBACK_FACTOR
        else:
            self.velocity.x = _kb.power[0] * CombatSettings.BLOCK_KNOCKBACK_FACTOR * direction

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
            return self._apply_block_damage_reaction(amount, knockback, source_center_x)

        result = super().receive_damage(amount, source_center_x, knockback, interrupt)

        if interrupt and hasattr(self.combat, "hurt_timer") and self.combat.hurt_timer > 0:
            self.combat.hurt_timer = min(
                self.combat.hurt_timer,
                CombatSettings.PLAYER_HURT_DURATION,
            )

        return result
