"""Base module for game entities with physics, health, and combat capabilities."""

import random
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from src.combat.knockback import KnockbackConfig
from src.combat.combatant_protocol import DamageResult
from src.combat.combat_component import CombatComponent, NullCombatComponent
from src.combat.attack_loading import load_attacks
from src.combat.damage_types import DamageType
from src.core.settings import Combat as CombatSettings, Physics
from src.physics import (
    apply_entity_gravity,
    apply_horizontal_movement,
    apply_moving_platform,
    move_entity,
    resolve_collisions,
    update_contact_state,
)
from src.states.null_state_machine import NullStateMachine


HEAVY_KNOCKBACK_THRESHOLD = 400.0



def compute_knockback_direction(
    hitbox_centerx: float,
    source_center_x: float | None,
    facing_right: bool,
) -> float:
    """Compute the horizontal direction of a knockback impulse.

    Parameters
    ----------
    hitbox_centerx : float
        The center X coordinate of the receiving entity.
    source_center_x : float | None
        The center X coordinate of the damage source.
    facing_right : bool
        The current facing direction of the entity.

    Returns
    -------
    float
        1.0 for right, -1.0 for left.
    """
    if source_center_x is not None:
        return 1.0 if hitbox_centerx >= source_center_x else -1.0
    return 1.0 if facing_right else -1.0


class Entity(Sprite):
    """Base class for any game entity with a hitbox, health, and combat capabilities.

    This class provides core functionality for movement, collision detection,
    health management, and combat interactions. It serves as the foundation
    for both player and enemy entities.

    Attributes
    ----------
    hitbox : pygame.FRect
        The collision hitbox for the entity.
    velocity : Vector2
        Current velocity vector (x, y).
    on_surface : dict[str, bool]
        Contact flags for floor, left wall, and right wall.
    health : float
        Current health points (clamped to [0, max_health]).
    max_health : float
        Maximum health cap.
    is_dead : bool
        Whether the entity has been defeated.
    facing_right : bool
        Current facing direction (True = right, False = left).
    """

    def __init__(
        self,
        pos: Sequence[float] | Vector2,
        size: Sequence[float],
        color: Sequence[int],
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        hitbox_inflate: Sequence[float] = (0.0, 0.0),
        hurtbox_inflate: Sequence[float] = (0.0, 0.0),
        health: float = 100.0,
        max_health: float = 100.0,
        faction: str = "neutral",
        spawn_pos: Sequence[float] | Vector2 | None = None,
        combat: CombatComponent | None = None,
        attacks: dict[str, Any] | None = None,
        hurt_duration: float | None = None,
        invincibility_duration: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        """Initialize the entity.

        Parameters
        ----------
        pos : Sequence[float] | Vector2
            Starting top-left position.
        size : Sequence[float]
            Width and height of the sprite surface.
        color : Sequence[int]
            Fill colour for the sprite surface.
        groups : Group | Sequence[Group]
            Sprite group(s) to add this entity to.
        collision_sprites : Group
            Group of sprites that block movement.
        hitbox_inflate : Sequence[float]
            (x, y) inflation for the physical collider relative to the rect.
        hurtbox_inflate : Sequence[float]
            Additional inflation for the damage-receiving area.
        health : float
            Starting health.
        max_health : float
            Maximum health cap.
        faction : str
            Faction for combat targeting.
        spawn_pos : Sequence[float] | Vector2 | None
            Respawn position; defaults to `pos`.
        combat : CombatComponent | None
            Optional custom combat component; otherwise NullCombatComponent.
        attacks : dict[str, Any] | None
            Dictionary of attack definitions to load into the combat component.
        hurt_duration : float | None
            Duration of the hurt state. Defaults to standard combat settings.
        invincibility_duration : float
            Duration of invincibility frames after taking damage.
        rng : random.Random | None
            Optional random number generator instance for deterministic behaviors.
        """
        super().__init__(groups)
        self.id: str = uuid.uuid4().hex
        self.pushable: bool = True
        self.faction: str = faction
        self.rng = rng or random.Random()

        self.image = pygame.Surface(size)
        self.image.fill(color)

        self.rect = self.image.get_frect(topleft=pos)
        self.hitbox = self.rect.inflate(*hitbox_inflate)
        self.hitbox.midbottom = self.rect.midbottom
        self.old_hitbox = self.hitbox.copy()
        self._hurtbox_inflate = tuple(hurtbox_inflate)
        self._hurtbox = self.hitbox.inflate(*self._hurtbox_inflate)

        self.collision_sprites = collision_sprites
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.velocity = Vector2(0, 0)

        self.move_axis: float = 0.0
        self.speed: float = 0.0
        self.floor_control: float = Physics.FLOOR_CONTROL
        self.air_control: float = Physics.AIR_CONTROL

        self.normal_gravity: float = Physics.GRAVITY
        self.fall_gravity: float = Physics.FALL_GRAVITY
        self.slide_gravity: float = Physics.GRAVITY * 0.15
        self.max_slide_speed: float = Physics.MAX_SLIDE_SPEED
        self.max_fall_speed: float = Physics.MAX_FALL_SPEED

        self.drag_coefficient: float = Physics.DRAG_COEFFICIENT
        self.fall_drag_coefficient: float = Physics.FALL_DRAG_COEFFICIENT

        self._health: float = health
        self._max_health: float = max_health
        self.is_dead: bool = False

        self.spawn_pos: Vector2 = Vector2(
            spawn_pos if spawn_pos is not None else pos)
        self.moving_platforms: list = []

        self.invincibility_timer: float = 0.0
        self.invincibility_duration: float = invincibility_duration

        if combat is not None:
            self.combat = combat
        elif attacks:
            self.combat = CombatComponent(
                self,
                combo_window=CombatSettings.COMBO_WINDOW,
                hurt_duration=hurt_duration or CombatSettings.HURT_DURATION,
            )
            load_attacks(self.combat, attacks)
        else:
            self.combat = NullCombatComponent()

        self.state_machine = NullStateMachine()
        self.facing_right: bool = True

        self.stagger_timer: float = 0.0
        self.super_armor: bool = False
        self.super_armor_count: int = 0

    def _setup_state_machine(self) -> None:
        """Initialize the state machine. Override in subclasses for specific states."""
        pass

    def _setup_interrupts(self) -> None:
        """Register shared state machine interrupts."""
        self.state_machine.add_interrupt(
            "hurt",
            lambda: self.combat.is_hurt,
            priority=100,
        )

    @property
    def health(self) -> float:
        """Current health, clamped to [0, max_health]."""
        return self._health

    @health.setter
    def health(self, value: float) -> None:
        """Set health, clamping to valid range and triggering death if needed.

        Parameters
        ----------
        value : float
            New health value.
        """
        old = self._health
        self._health = max(0.0, min(value, self._max_health))
        if old > 0 and self._health == 0 and not self.is_dead:
            self.die()

    @property
    def max_health(self) -> float:
        """Maximum health cap."""
        return self._max_health

    @max_health.setter
    def max_health(self, value: float) -> None:
        """Set maximum health, ensuring it's at least 1.0.

        Parameters
        ----------
        value : float
            New maximum health value.
        """
        self._max_health = max(1.0, value)

    def die(self) -> None:
        """Mark the entity as dead and clear transient offensive state."""
        self.is_dead = True
        self.combat.reset()

    @property
    def hurtbox(self) -> pygame.FRect:
        """Damage-receiving area, distinct from the physical collider."""
        return self._hurtbox

    @property
    def has_super_armor(self) -> bool:
        """Whether the entity currently ignores stagger."""
        return self.super_armor

    def break_super_armor(self) -> None:
        """Remove super armor and reset the hit counter."""
        self.super_armor = False
        self.super_armor_count = 0

    def get_damage_modifier(self, damage_type: DamageType) -> float:
        """Damage multiplier for a given damage type.

        Override in subclasses for resistances/vulnerabilities.

        Parameters
        ----------
        damage_type : DamageType
            The category of incoming damage.

        Returns
        -------
        float
            Multiplier applied to the raw damage amount.
        """
        return 1.0

    def sync_rects(self) -> None:
        """Align sprite and hurtbox geometry with the physical collider."""
        self.rect.midbottom = self.hitbox.midbottom
        inflate_x, inflate_y = self._hurtbox_inflate
        self._hurtbox.size = (
            self.hitbox.width + inflate_x,
            self.hitbox.height + inflate_y,
        )
        self._hurtbox.center = self.hitbox.center

    def face_movement(self, threshold: float = 0.1) -> None:
        """Orient the entity based on its current movement axis.

        Parameters
        ----------
        threshold : float
            The minimum axis magnitude to trigger a direction change.
        """
        if self.move_axis > threshold:
            self.facing_right = True
        elif self.move_axis < -threshold:
            self.facing_right = False

    def face_towards(self, x: float, threshold: float = 2.0) -> None:
        """Orient the entity toward a specific X coordinate.

        Parameters
        ----------
        x : float
            The target X-coordinate to face.
        threshold : float
            The minimum distance to trigger a direction change, preventing rapid toggling.
        """
        if abs(x - self.hitbox.centerx) > threshold:
            self.facing_right = x > self.hitbox.centerx

    def _is_wall_sliding(self) -> bool:
        """Return True if the entity is currently sliding down a wall."""
        return False

    def _on_floor_contact(self) -> None:
        """Called when the entity lands on the floor."""
        pass

    def _on_wall_contact(self) -> None:
        """Called when the entity touches a wall while airborne."""
        pass

    def apply_gravity(self, delta_time: float) -> None:
        """Apply gravity with drag, respecting wall sliding."""
        apply_entity_gravity(self, delta_time)

    def apply_horizontal_movement(self, delta_time: float) -> None:
        """Apply horizontal acceleration and control based on move_axis."""
        apply_horizontal_movement(self, delta_time)

    def check_contact(self) -> None:
        """Update surface contact flags."""
        update_contact_state(self, self.collision_sprites)

    def handle_collisions(self, axis: str) -> None:
        """Resolve collisions along a given axis."""
        resolve_collisions(self, axis)

    def move(self, delta_time: float, apply_gravity: bool = True) -> None:
        """Move the entity based on velocity, resolving collisions."""
        move_entity(self, delta_time, apply_gravity=apply_gravity)

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        """Carry the entity along moving platforms."""
        apply_moving_platform(self, moving_platforms)

    def reset_position(self) -> None:
        """Reset the entity to its spawn position and clear all states.

        This method resets position, velocity, health, and various timers.
        It also changes the state machine to idle state if available.
        """
        self.hitbox.center = self.spawn_pos
        self.sync_rects()
        self.velocity = Vector2(0, 0)
        self.old_hitbox = self.hitbox.copy()
        self.is_dead = False
        self.stagger_timer = 0.0
        self.super_armor = False
        self.super_armor_count = 0
        self.invincibility_timer = 0.0
        self.health = self.max_health

        self.combat.reset()

        if hasattr(self.state_machine, 'change_state'):
            self.state_machine.change_state("idle", force=True)

        self._on_reset()

    def _on_reset(self) -> None:
        """Hook for subclasses to reset their specific state."""
        pass

    def _can_receive_damage(self) -> bool:
        """Check if the entity can currently receive damage. Override to add immunities."""
        return not self.is_dead and self.invincibility_timer <= 0

    def _apply_damage(self, amount: float) -> float:
        """Subtract health points and return actual damage dealt.

        Parameters
        ----------
        amount : float
            Damage amount to apply.

        Returns
        -------
        float
            Actual damage dealt.
        """
        old_health = self._health
        self.health -= amount
        return old_health - self.health

    def _apply_knockback(
        self,
        knockback: KnockbackConfig,
        source_center_x: float | None,
    ) -> None:
        """Apply knockback velocity based on the configuration and source position.

        Parameters
        ----------
        knockback : KnockbackConfig
            Configuration for the push effect.
        source_center_x : float | None
            X-coordinate of the damage source for knockback direction.
        """
        if knockback.power == (0.0, 0.0):
            return

        if knockback.mode == "fixed":
            self.velocity.x = knockback.power[0]
            self.velocity.y = knockback.power[1]
        else:
            direction = compute_knockback_direction(
                self.hitbox.centerx, source_center_x, self.facing_right
            )
            self.velocity.x = knockback.power[0] * direction
            self.velocity.y = knockback.power[1]

    def _handle_heavy_knockback(
        self,
        knockback: KnockbackConfig,
        source_center_x: float | None,
    ) -> bool:
        """Trigger the launch state for knockback at or above the heavy threshold.

        The full vector magnitude is used so upward launches and combined diagonal
        impulses are classified consistently.

        Parameters
        ----------
        knockback : KnockbackConfig
            Configuration for the push effect.
        source_center_x : float | None
            X-coordinate of the damage source for knockback direction.
        """
        kb_power_x, kb_power_y = knockback.power
        magnitude = Vector2(kb_power_x, kb_power_y).length()
        if magnitude < HEAVY_KNOCKBACK_THRESHOLD:
            return False

        # Cancel an active action before selecting knockback as the definitive
        # reaction. This avoids a simultaneous hurt/knockback state.
        self.combat.on_hit(interrupt=True)
        direction = compute_knockback_direction(
            self.hitbox.centerx, source_center_x, self.facing_right
        )
        self.state_machine.change_state(
            "knockback",
            force=True,
            knockback_direction=direction,
            knockback_force=kb_power_x,
            knockback_up_force=kb_power_y,
        )
        if hasattr(self.combat, "is_hurt"):
            self.combat.is_hurt = False
        return True

    def receive_damage(
        self,
        amount: float,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
    ) -> DamageResult:
        """Public entry point for applying damage, knockback, and hit reactions.

        Parameters
        ----------
        amount : float
            Raw damage (will be modified by resistances in subclasses).
        source_center_x : float | None
            X-coordinate of the damage source for knockback direction.
        knockback : KnockbackConfig | None
            Configuration for the push effect.
        interrupt : bool
            Whether to interrupt current actions.

        Returns
        -------
        DamageResult
            A dataclass detailing the outcome of the damage application.
        """
        if not self._can_receive_damage():
            return DamageResult()

        actual_damage = self._apply_damage(amount)

        if knockback is not None:
            self._apply_knockback(knockback, source_center_x)

        if self.invincibility_duration > 0:
            self.invincibility_timer = self.invincibility_duration

        heavy_knockback = False
        if interrupt and not self.is_dead and knockback is not None:
            heavy_knockback = self._handle_heavy_knockback(
                knockback, source_center_x
            )

        return DamageResult(
            applied=actual_damage > 0,
            killed=self.is_dead,
            actual_damage=actual_damage,
            heavy_knockback=heavy_knockback,
        )

    def stagger(self, duration: float) -> None:
        """Apply stagger, handling super armor and stunlock protection.

        Super armor is consumed after `SUPER_ARMOR_THRESHOLD` hits.
        If the entity has super armor and the threshold is not reached,
        no stagger is applied.

        Parameters
        ----------
        duration : float
            The duration of the stagger in seconds.
        """
        if self.is_dead or self.stagger_timer > 0:
            return

        if self.super_armor:
            self.super_armor_count += 1
            if self.super_armor_count < CombatSettings.SUPER_ARMOR_THRESHOLD:
                return
            self.super_armor = False

        self.stagger_timer = duration
        self.combat.reset_hurt_state()
        self.state_machine.change_state("stagger", force=True)

    def _pre_update(self, delta_time: float) -> None:
        """Hook called at the beginning of the update loop, before combat and physics."""
        pass

    def _update_state_machine(self, delta_time: float) -> None:
        """Update the state machine. Can be overridden to disable AI dynamically."""
        self.state_machine.update(delta_time)

    def _post_update(self, delta_time: float) -> None:
        """Hook called at the end of the update loop, after physics."""
        pass

    def update(self, delta_time: float) -> None:
        """Main update loop template handling timers, combat, state, and movement.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        """
        if self.is_dead:
            return

        self.old_hitbox = self.hitbox.copy()

        if self.stagger_timer > 0:
            self.stagger_timer -= delta_time
            if self.stagger_timer < 0:
                self.stagger_timer = 0.0

        if self.invincibility_timer > 0:
            self.invincibility_timer -= delta_time
            if self.invincibility_timer < 0:
                self.invincibility_timer = 0.0

        self._pre_update(delta_time)
        self._update_state_machine(delta_time)
        self.combat.update(delta_time)
        self.move(delta_time, apply_gravity=True)
        self.combat.sync_attack_box()
        self._post_update(delta_time)
