"""Base module for game entities with physics, health, and combat capabilities."""

import uuid
from collections.abc import Iterable, Sequence
from typing import Any, Optional, Union

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from src.combat.knockback import KnockbackConfig
from src.combat.combat_component import CombatComponent, NullCombatComponent
from src.combat.damage_types import DamageType
from src.core.settings import Combat as CombatSettings, Physics
from src.physics import (
    apply_entity_gravity,
    apply_moving_platform,
    move_entity,
    resolve_collisions,
    update_contact_state,
)
from src.states.null_state_machine import NullStateMachine


class Entity(Sprite):
    """Base class for any game entity with a hitbox, health, and combat capabilities.

    Attributes
    ----------
    hitbox : pygame.FRect
        The physical collision box.
    old_hitbox : pygame.FRect
        Previous frame's hitbox for collision resolution.
    collision_sprites : Group
        All sprites that block movement.
    on_surface : dict[str, bool]
        Contact flags: floor, left, right.
    velocity : Vector2
        Current speed in pixels per second.
    normal_gravity : float
        Gravity when moving upward or stationary.
    fall_gravity : float
        Gravity when falling (can be higher).
    slide_gravity : float
        Gravity applied during wall sliding.
    max_slide_speed : float
        Maximum downward speed while sliding.
    max_fall_speed : float
        Terminal velocity.
    drag_coefficient : float
        Air resistance during upward movement.
    fall_drag_coefficient : float
        Air resistance during downward movement.
    health : float
        Current hit points.
    max_health : float
        Maximum hit points.
    is_dead : bool
        True if health <= 0 and die() has been called.
    spawn_pos : Vector2
        Initial position for respawning.
    moving_platforms : list
        Platforms that carry the entity.
    combat : CombatComponent | NullCombatComponent
        Attack/defense state.
    state_machine : StateMachine
        State machine for AI or player behaviour.
    facing_right : bool
        Visual direction.
    stagger_timer : float
        Remaining time of forced stagger.
    super_armor : bool
        Whether the entity ignores stagger.
    super_armor_count : int
        Number of hits received while super_armor active.
    pushable : bool
        Whether the entity can be pushed by separation system.
    faction : str
        Faction identifier ("player", "enemy", "neutral", etc.).
    """

    hitbox: pygame.FRect
    old_hitbox: pygame.FRect
    collision_sprites: Group
    on_surface: dict[str, bool]
    velocity: Vector2
    normal_gravity: float
    slide_gravity: float
    max_slide_speed: float
    fall_gravity: float
    max_fall_speed: float
    drag_coefficient: float
    fall_drag_coefficient: float

    def __init__(
        self,
        pos: Union[Sequence[float], Vector2],
        size: Sequence[float],
        color: Sequence[int],
        groups: Union[Group, Sequence[Group]],
        collision_sprites: Group,
        hitbox_inflate: Sequence[float] = (0.0, 0.0),
        health: float = 100.0,
        max_health: float = 100.0,
        faction: str = "neutral",
        spawn_pos: Optional[Union[Sequence[float], Vector2]] = None,
        combat: Optional[CombatComponent] = None,
    ) -> None:
        """Initialize the entity.

        Parameters
        ----------
        pos : Union[Sequence[float], Vector2]
            Starting top-left position.
        size : Sequence[float]
            Width and height of the sprite surface.
        color : Sequence[int]
            Fill colour for the sprite surface.
        groups : Union[Group, Sequence[Group]]
            Sprite group(s) to add this entity to.
        collision_sprites : Group
            Group of sprites that block movement.
        hitbox_inflate : Sequence[float]
            (x, y) inflation for the hitbox relative to the rect.
        health : float
            Starting health.
        max_health : float
            Maximum health cap.
        faction : str
            Faction for combat targeting.
        spawn_pos : Optional[Union[Sequence[float], Vector2]]
            Respawn position; defaults to `pos`.
        combat : Optional[CombatComponent]
            Optional custom combat component; otherwise NullCombatComponent.
        """
        super().__init__(groups)
        self.id: str = uuid.uuid4().hex
        self.pushable: bool = True
        self.faction: str = faction

        self.image = pygame.Surface(size)
        self.image.fill(color)

        self.rect = self.image.get_frect(topleft=pos)
        self.hitbox = self.rect.inflate(*hitbox_inflate)
        self.hitbox.midbottom = self.rect.midbottom
        self.old_hitbox = self.hitbox.copy()

        self.collision_sprites = collision_sprites
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.velocity = Vector2(0, 0)

        self.normal_gravity = Physics.GRAVITY
        self.fall_gravity = Physics.FALL_GRAVITY
        self.slide_gravity = Physics.GRAVITY * 0.15
        self.max_slide_speed = 80.0
        self.max_fall_speed = Physics.MAX_FALL_SPEED

        self.drag_coefficient = 0.08
        self.fall_drag_coefficient = 0.12

        self._health = health
        self._max_health = max_health
        self.is_dead = False

        self.spawn_pos = Vector2(spawn_pos if spawn_pos is not None else pos)
        self.moving_platforms: list = []
        self.combat: Union[CombatComponent, NullCombatComponent] = (
            combat or NullCombatComponent()
        )
        self.state_machine = NullStateMachine()
        self.facing_right = True

        self.stagger_timer = 0.0
        self.super_armor = False
        self.super_armor_count = 0

    @property
    def health(self) -> float:
        """Current health, clamped to [0, max_health]."""
        return self._health

    @health.setter
    def health(self, value: float) -> None:
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
        self._max_health = max(1.0, value)

    def die(self) -> None:
        """Mark the entity as dead and perform cleanup."""
        self.is_dead = True

    @property
    def hurtbox(self) -> pygame.FRect:
        """Hitbox used for incoming damage detection."""
        return self.hitbox

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
        """Align the sprite rect with the hitbox (midbottom anchor)."""
        self.rect.midbottom = self.hitbox.midbottom

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
        """Apply gravity with drag, respecting wall sliding.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        """
        apply_entity_gravity(self, delta_time)

    def check_contact(self) -> None:
        """Update surface contact flags."""
        update_contact_state(self, self.collision_sprites)

    def handle_collisions(self, axis: str) -> None:
        """Resolve collisions along a given axis.

        Parameters
        ----------
        axis : str
            The axis to resolve collisions on ('x' or 'y').
        """
        resolve_collisions(self, axis)

    def move(self, delta_time: float, apply_gravity: bool = True) -> None:
        """Move the entity based on velocity, resolving collisions.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        apply_gravity : bool
            Whether to apply gravity this frame.
        """
        move_entity(self, delta_time, apply_gravity=apply_gravity)

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        """Carry the entity along moving platforms.

        Parameters
        ----------
        moving_platforms : Iterable[Any]
            An iterable of moving platform sprites.
        """
        apply_moving_platform(self, moving_platforms)

    def reset_position(self) -> None:
        """Reset the entity to its spawn position and clear all states."""
        self.hitbox.center = self.spawn_pos
        self.sync_rects()
        self.velocity = Vector2(0, 0)
        self.old_hitbox = self.hitbox.copy()
        self.is_dead = False
        self.stagger_timer = 0.0
        self.super_armor = False
        self.super_armor_count = 0
        self.health = self.max_health

    def _apply_damage(self, amount: int) -> None:
        """Subtract health points and trigger death if health reaches zero.

        This is a separate method to allow overriding or extending.

        Parameters
        ----------
        amount : int
            The amount of hit points to subtract.
        """
        self.health -= amount

    def _apply_knockback(
        self,
        knockback: KnockbackConfig,
        source_center_x: Optional[float],
    ) -> None:
        """Apply knockback velocity based on the configuration and source position.

        For 'from_attacker' mode, the horizontal direction is derived from
        the source's x‑coordinate relative to this entity's hitbox.
        For 'fixed' mode, the power is applied as‑is.

        Parameters
        ----------
        knockback : KnockbackConfig
            Configuration for the push effect.
        source_center_x : Optional[float]
            X‑coordinate of the damage source for knockback direction.
        """
        if knockback.power == (0.0, 0.0):
            return

        if knockback.mode == "fixed":
            self.velocity.x = knockback.power[0]
            self.velocity.y = knockback.power[1]
        else:
            if source_center_x is not None:
                direction = 1.0 if self.hitbox.centerx >= source_center_x else -1.0
            else:
                direction = 1.0 if getattr(
                    self, "facing_right", True) else -1.0
            self.velocity.x = knockback.power[0] * direction
            self.velocity.y = knockback.power[1]

    def receive_damage(
        self,
        amount: int,
        source_center_x: Optional[float] = None,
        knockback: Optional[KnockbackConfig] = None,
        interrupt: bool = True,
    ) -> None:
        """Public entry point for applying damage, knockback, and hit reactions.

        Parameters
        ----------
        amount : int
            Raw damage (will be modified by resistances in subclasses).
        source_center_x : Optional[float]
            X‑coordinate of the damage source for knockback direction.
        knockback : Optional[KnockbackConfig]
            Configuration for the push effect.
        interrupt : bool
            Whether to interrupt current actions (handled by HitResolver).
        """
        if self.is_dead:
            return

        self._apply_damage(amount)

        if knockback is not None:
            self._apply_knockback(knockback, source_center_x)

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
        self.combat.is_hurt = False
        self.combat._hurt_timer = 0.0
        self.state_machine.change_state("stagger", force=True)

    def update(self, delta_time: float) -> None:
        """Update timers and state; called every frame.

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
