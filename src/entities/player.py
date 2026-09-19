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
from src.core.settings import Guard as GuardSettings
from src.core.settings import HitFlash, Physics
from src.entities.controller_view import ControllerView
from src.entities.entity import Entity, EntitySnapshot, compute_knockback_direction
from src.entities.player_animation import PLAYER_ANIMATIONS
from src.entities.player_config import DEFAULT_PLAYER_CONFIG, PlayerConfig
from src.entities.player_controllers import (
    DashController,
    GuardController,
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
    """Playable character with movement, guard, dash, and frame-data attacks."""

    input_manager: InputManager
    speed: float
    floor_control: float
    air_control: float

    jump: JumpController
    guard: GuardController
    dash: DashController
    input_handler: PlayerInputHandler

    moving_platforms: Iterable[Any]

    left_held: bool
    right_held: bool
    guard_held: bool

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
        # Guard controller (debug UI, hit resolver)
        "guard_posture": ("guard", "posture"),
        "guard_posture_max": ("guard", "max_posture"),
        "guard_lockout_timer": ("guard", "lockout_timer"),
        "guard_parry_timer": ("guard", "parry_timer"),
        "guard_riposte_timer": ("guard", "riposte_timer"),
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
        self.guard = GuardController(config)
        self.dash = DashController(config, original_hitbox_width=self.hitbox.width)

        self.moving_platforms = moving_platforms

        self.left_held = False
        self.right_held = False
        self.guard_held = False

        self.input_manager = input_manager
        self.input_handler = PlayerInputHandler(self)

        self.animator = Animator(shared_library(), PLAYER_ANIMATIONS, default="idle")
        self._setup_state_machine()

    def _setup_state_machine(self) -> None:
        configure_player_state_machine(self)
        self._setup_interrupts()

    def _setup_interrupts(self) -> None:
        super()._setup_interrupts()

    @property
    def is_guarding(self) -> bool:
        return self.state_machine.current_state_name == PlayerState.GUARD

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
        is_guarding = self.state_machine.current_state_name == PlayerState.GUARD
        self.jump.update(delta_time, self.on_surface["floor"])
        self.guard.update(delta_time, is_guarding)
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
            PlayerState.DASH: "dash",
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
        self.jump.reset()
        self.guard.reset()
        self.dash.reset()
        self.move_axis = 0.0
        self.input_handler.buffered_attack_name = None
        self.hitbox.width = self.dash.original_hitbox_width

        self.left_held = False
        self.right_held = False
        self.guard_held = False

    def respawn(self) -> None:
        self.reset_position()

    def _faces_source(self, source_center_x: float | None) -> bool:
        if source_center_x is None:
            return True
        if source_center_x >= self.hitbox.centerx:
            return self.facing_right
        return not self.facing_right

    def _apply_guard_reaction(
        self,
        amount: float,
        knockback: KnockbackConfig | None,
        source_center_x: float | None,
    ) -> DamageResult:
        _kb = knockback if knockback is not None else NULL_KNOCKBACK
        in_air = not self.on_surface["floor"]
        outcome, chip, was_parry = self.guard.take_hit(amount, in_air)
        if outcome == "parry":
            self.parries_given += 1
            self._reaction.note_guard_push(_kb, source_center_x, parried=True)
            return DamageResult(guarded=True, parried=True)
        direction = compute_knockback_direction(
            self.hitbox.centerx, source_center_x, self.facing_right
        )
        if _kb.mode == "fixed":
            push_dir = 1.0 if _kb.power[0] >= 0.0 else -1.0
            self.velocity.x = _kb.power[0] * GuardSettings.PUSH_FACTOR
            direction = push_dir
        else:
            self.velocity.x = _kb.power[0] * GuardSettings.PUSH_FACTOR * direction
        self._reaction.note_guard_push(_kb, source_center_x)
        if chip > 0:
            self._apply_damage(chip)
            self.flash_timer = HitFlash.DURATION
        if outcome == "break":
            self.stagger(GuardSettings.BREAK_STAGGER)
            return DamageResult(guarded=True, guard_broken=True, applied=True, actual_damage=chip)
        return DamageResult(guarded=True, applied=False, actual_damage=chip)

    def receive_damage(
        self,
        amount: float,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
    ) -> DamageResult:
        if not self._can_receive_damage():
            return DamageResult()

        # Perfect Dash Parry: if dashing within parry window, auto-parry
        if self.state_machine.current_state_name == "dash":
            dash_elapsed = self.dash.duration - self.dash.duration_timer
            if dash_elapsed <= Physics.DASH_PARRY_WINDOW:
                # Perfect parry: no damage, restore posture, grant riposte
                self.guard.posture = self.guard.max_posture
                self.guard.riposte_timer = GuardSettings.RIPOSTE_WINDOW
                self.parries_given += 1
                self._reaction.note_guard_push(knockback or NULL_KNOCKBACK, source_center_x, parried=True)
                self.flash_timer = HitFlash.DURATION
                return DamageResult(guarded=True, parried=True)

        if self.is_guarding and self._faces_source(source_center_x):
            return self._apply_guard_reaction(amount, knockback, source_center_x)

        result = super().receive_damage(amount, source_center_x, knockback, interrupt)

        if interrupt and hasattr(self.combat, "hurt_timer") and self.combat.hurt_timer > 0:
            self.combat.hurt_timer = min(
                self.combat.hurt_timer,
                CombatSettings.PLAYER_HURT_DURATION,
            )

        return result

    def save_state(self) -> EntitySnapshot:
        snapshot = super().save_state()
        snapshot.extra = {
            "jump": self.jump.save_state(),
            "guard": self.guard.save_state(),
            "dash": self.dash.save_state(),
            "buffered_attack_name": self.input_handler.buffered_attack_name,
            "left_held": self.left_held,
            "right_held": self.right_held,
            "guard_held": self.guard_held,
        }
        return snapshot

    def load_state(self, snapshot: EntitySnapshot) -> None:
        super().load_state(snapshot)
        extra = snapshot.extra
        self.jump.load_state(extra["jump"])
        self.guard.load_state(extra["guard"])
        self.dash.load_state(extra["dash"])
        self.input_handler.buffered_attack_name = extra["buffered_attack_name"]
        self.left_held = extra["left_held"]
        self.right_held = extra["right_held"]
        self.guard_held = extra["guard_held"]
