"""Base module for game entities with physics, health, and combat capabilities."""

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Literal, cast

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from src.combat.attack_loading import load_attacks
from src.combat.combat_component import CombatComponent, CombatSnapshot, NullCombatComponent
from src.combat.combatant_protocol import DamageResult
from src.combat.damage_types import DamageType
from src.combat.knockback import KnockbackConfig
from src.combat.sweep import swept_box
from src.core.animation.animator import Animator
from src.core.settings import Combat as CombatSettings
from src.core.settings import EnemyJump, HitFlash, Ledge, Physics
from src.entities.components import MovementComponent, ReactionComponent
from src.entities.components.reaction import (
    ReactionStatus,
    compute_knockback_direction,
)
from src.entities.hurtbox_zones import HurtboxZoneDef
from src.entities.vitals import Vitals, VitalsSnapshot
from src.physics import SpatialHash
from src.physics.collisions import CollisionSprite, get_nearby_sprites
from src.states.null_state_machine import NullStateMachine
from src.states.state_machine import StateMachine, StateMachineSnapshot

# Deterministic entity identifier source (ARCH-08).  A sequential counter
# yields identical IDs for identically-ordered simulations, which keeps
# rollback and future netcode in sync (unlike a random UUID).
_ENTITY_ID_SEQUENCE = count()

# ``compute_knockback_direction`` now lives in the reaction component; it is
# re-exported here so the historical ``from src.entities.entity import
# compute_knockback_direction`` (used by ``Player``) keeps working.
__all__ = ["Entity", "compute_knockback_direction"]


@dataclass
class EntitySnapshot:
    """Serializable capture of an entity's full simulation state (Phase 3 #3).

    Holds a direct reference to the live entity so a *local* rollback
    (``RollbackSystem``) can resurrect a sprite that has since been
    ``kill()``-ed and re-add it to its recorded groups.  The data fields are
    plain/pickle-free scalars and tuples — the parts a future network
    rollback would serialize — while ``entity`` and ``groups`` are local-only.
    """

    entity: Any
    entity_id: str
    hitbox: tuple[float, float, float, float]
    old_hitbox: tuple[float, float, float, float]
    velocity: tuple[float, float]
    on_surface: dict[str, bool]
    facing_right: bool
    move_axis: float
    pushable: bool
    rng_state: tuple[Any, ...]
    vitals: VitalsSnapshot
    combat: CombatSnapshot
    state_machine: StateMachineSnapshot
    groups: list[Any] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


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
    spatial_hash : SpatialHash | None
        Collision grid shared with the level; queried by ``move`` for O(1)
        neighbor lookups. Assigned by the level after the world is built.
    """

    # Kinematic state is owned by ``self._movement`` (MovementComponent) and
    # exposed through the ``velocity`` / ``on_surface`` delegating properties
    # below.  Class-level annotations were removed: they collided with the
    # same-named properties (mypy no-redef) and the property docstrings
    # already document the public contract on the entity facade.

    def __init__(
        self,
        pos: Sequence[float] | Vector2,
        size: Sequence[float],
        color: Sequence[int],
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        hitbox_inflate: Sequence[float] = (0.0, 0.0),
        hurtbox_inflate: Sequence[float] = (0.0, 0.0),
        hurtbox_zones: Sequence[HurtboxZoneDef] | None = None,
        health: float = 100.0,
        max_health: float = 100.0,
        faction: str = "neutral",
        spawn_pos: Sequence[float] | Vector2 | None = None,
        combat: CombatComponent | None = None,
        attacks: Mapping[str, Any] | None = None,
        hurt_duration: float | None = None,
        invincibility_duration: float = 0.0,
        rng: random.Random | None = None,
        entity_id: str | None = None,
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
        attacks : Mapping[str, Any] | None
            Dictionary of attack definitions to load into the combat component.
        hurt_duration : float | None
            Duration of the hurt state. Defaults to standard combat settings.
        invincibility_duration : float
            Duration of invincibility frames after taking damage.
        rng : random.Random | None
            Optional random number generator instance for deterministic behaviors.
        """
        super().__init__(groups)
        self.id: str = entity_id if entity_id is not None else f"e{next(_ENTITY_ID_SEQUENCE)}"
        self.pushable: bool = True
        self.faction: str = faction
        self.rng = rng or random.Random()

        self.image = pygame.Surface(size)
        self.image.fill(color)

        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        # P2 (axe B): the physical collider is the *pushbox*. ``hitbox`` stays
        # as a delegating property over the same FRect for one release — no
        # caller migrated at this tier (checklist P2.5).
        self._pushbox = self.rect.inflate(*hitbox_inflate)
        self._pushbox.midbottom = self.rect.midbottom
        self.old_hitbox = self._pushbox.copy()
        self._hurtbox_inflate: tuple[float, float] = (
            float(hurtbox_inflate[0]),
            float(hurtbox_inflate[1]),
        )
        # P2 multi-hurtbox: zones derive from the pushbox via ``sync_rects``
        # (the single derivation point, preserving the dash-squish timing).
        # ``None`` config = one legacy zone = exact pre-P2 behavior.
        self._zones: tuple[HurtboxZoneDef, ...] = (
            tuple(hurtbox_zones)
            if hurtbox_zones is not None
            else (HurtboxZoneDef(inflate=self._hurtbox_inflate),)
        )
        self._hurtbox_rects: list[pygame.FRect] = []
        self._hurtbox_union: pygame.FRect = pygame.FRect(0, 0, 0, 0)
        # P1 sweep origins, now per zone (P2: ``_prev_hurtbox`` -> tuple).
        # Written only by ``capture_sweep_origin`` (tick frontier), reset by
        # ``reset_position``/``load_state`` (no stale smear across a teleport
        # or a rollback; re-derived at the next capture).
        self._prev_hurtboxes: tuple[pygame.FRect, ...] = ()
        # Initial derivation (the legacy code built ``_hurtbox`` inline here).
        self.sync_rects()

        self.collision_sprites: Iterable[CollisionSprite] = cast(
            Iterable[CollisionSprite], collision_sprites
        )
        # Shared collision grid (PERF-01): assigned by the Level after the
        # world is built; ``move_entity`` queries it for O(1) neighbor lookups.
        self.spatial_hash: SpatialHash | None = None
        # Kinematic state (velocity, surface contacts) is owned by the
        # MovementComponent (Phase 3 #2); ``Entity`` exposes it via delegating
        # properties so the historical ``entity.velocity``/``entity.on_surface``
        # API — and the pure ``src.physics`` functions that read them off the
        # entity — keep working unchanged.
        self._movement = MovementComponent(self)

        self.move_axis: float = 0.0
        self.speed: float = 0.0
        self.floor_control: float = Physics.FLOOR_CONTROL
        self.air_control: float = Physics.AIR_CONTROL

        self.normal_gravity: float = Physics.GRAVITY
        self.fall_gravity: float = Physics.FALL_GRAVITY
        self.slide_gravity: float = Physics.GRAVITY * 0.15
        self.max_slide_speed: float = Physics.MAX_SLIDE_SPEED
        self.max_fall_speed: float = Physics.MAX_FALL_SPEED
        # Phase 5 #4 (juggle): gravity multiplier while juggled, OTG guard
        # granted on landing from a juggle. Timers tick in ``update``.
        self.gravity_scale: float = 1.0
        # Fast fall: set from the down action while airborne (GameFeel).
        self.fast_fall: bool = False
        self.juggle_timer: float = 0.0
        self.otg_timer: float = 0.0
        # Render-only damage flash (never snapshotted, never in goldens).
        self.flash_timer: float = 0.0
        # Render-only freshness of the last hit reaction (armed by
        # ReactionComponent, decayed in ``update``); never snapshotted.
        self.reaction_age: float = 0.0
        # Render-only landing hint: pre-move fall speed captured on the
        # landing tick (PhysicsSystem turns hard landings into dust puffs).
        # Never snapshotted, never in goldens.
        self.landed_impact: float = 0.0
        # Parry-stun counters (reset on rollback/load, consecutive logic).
        self.parries_given: int = 0
        self.parries_taken: int = 0
        # Per-entity parry-stun config (copied from config on spawn).
        self.parry_stun_threshold: int | None = None
        self.parry_stun_duration: float = 0.0
        # Physics robustness: crush flag set by the bounded resolver and
        # pre-carry backup for crush revert (both tick in ``update``).
        self.crushed: bool = False
        self.carry_backup: tuple[float, float, float, float] | None = None

        self.drag_coefficient: float = Physics.DRAG_COEFFICIENT
        self.fall_drag_coefficient: float = Physics.FALL_DRAG_COEFFICIENT

        self.moving_platforms: Iterable[Any] = []
        self.vitals = Vitals(
            health=health,
            max_health=max_health,
            invincibility_duration=invincibility_duration,
            spawn_pos=Vector2(spawn_pos if spawn_pos is not None else pos),
            on_death=self._handle_death,
        )

        if combat is not None:
            self.combat: CombatComponent | NullCombatComponent = combat
        elif attacks:
            self.combat = CombatComponent(
                self,
                combo_window=CombatSettings.COMBO_WINDOW,
                hurt_duration=hurt_duration or CombatSettings.HURT_DURATION,
            )
            load_attacks(self.combat, attacks)
        else:
            self.combat = NullCombatComponent()

        self.state_machine: StateMachine | NullStateMachine = NullStateMachine()
        self.facing_right: bool = True
        # Hit-reaction rules (knockback, heavy launch, stagger) live in the
        # ReactionComponent (Phase 3 #2), wired in like ``vitals``/``combat``.
        # It is built after them because it drives both on reaction.
        self._reaction = ReactionComponent(self)
        # Optional sprite animation (Phase 2 #1): subclasses attach an
        # Animator; entities without one keep their flat colored surface.
        self.animator: Animator | None = None

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

    # ------------------------------------------------------------------
    # Health and status timers are owned by ``self.vitals`` and exposed
    # here as delegating attributes to preserve the historical Entity API.
    # ------------------------------------------------------------------

    @property
    def health(self) -> float:
        """Current health, clamped to [0, max_health]."""
        return self.vitals.health

    @health.setter
    def health(self, value: float) -> None:
        """Set health, clamping to valid range and triggering death if needed."""
        self.vitals.health = value

    @property
    def max_health(self) -> float:
        """Maximum health cap."""
        return self.vitals.max_health

    @max_health.setter
    def max_health(self, value: float) -> None:
        """Set maximum health, ensuring it's at least 1.0."""
        self.vitals.max_health = value

    @property
    def is_dead(self) -> bool:
        """Whether the entity has been defeated."""
        return self.vitals.is_dead

    @is_dead.setter
    def is_dead(self, value: bool) -> None:
        self.vitals.is_dead = value

    @property
    def spawn_pos(self) -> Vector2:
        """Position used to reset the entity after death."""
        return self.vitals.spawn_pos

    @spawn_pos.setter
    def spawn_pos(self, value: Vector2) -> None:
        self.vitals.spawn_pos = value

    @property
    def invincibility_timer(self) -> float:
        """Remaining invincibility time in seconds."""
        return self.vitals.invincibility_timer

    @invincibility_timer.setter
    def invincibility_timer(self, value: float) -> None:
        self.vitals.invincibility_timer = value

    @property
    def invincibility_duration(self) -> float:
        """Duration of invincibility frames after taking damage."""
        return self.vitals.invincibility_duration

    @invincibility_duration.setter
    def invincibility_duration(self, value: float) -> None:
        self.vitals.invincibility_duration = value

    @property
    def stagger_timer(self) -> float:
        """Remaining stagger time in seconds."""
        return self.vitals.stagger_timer

    @stagger_timer.setter
    def stagger_timer(self, value: float) -> None:
        self.vitals.stagger_timer = value

    @property
    def super_armor(self) -> bool:
        """Whether the entity currently ignores stagger."""
        return self.vitals.super_armor

    @super_armor.setter
    def super_armor(self, value: bool) -> None:
        self.vitals.super_armor = value

    @property
    def super_armor_count(self) -> int:
        """Consecutive hits absorbed by super armor."""
        return self.vitals.super_armor_count

    @super_armor_count.setter
    def super_armor_count(self, value: int) -> None:
        self.vitals.super_armor_count = value

    # ------------------------------------------------------------------
    # Kinematic state is owned by ``self._movement`` and exposed here as
    # delegating properties. The getter returns the component's live, mutable
    # object so in-place writes (``entity.velocity.x = ...``,
    # ``entity.on_surface["floor"] = ...`` — used throughout ``src.physics``
    # and the state machine) reach the single source of truth; the setter
    # supports whole-object replacement (``entity.velocity = Vector2(...)``).
    # ------------------------------------------------------------------

    @property
    def velocity(self) -> Vector2:
        """Current velocity vector, owned by the movement component."""
        return self._movement.velocity

    @velocity.setter
    def velocity(self, value: Vector2) -> None:
        self._movement.velocity = value

    @property
    def on_surface(self) -> dict[str, bool]:
        """Floor/left/right contact flags, owned by the movement component."""
        return self._movement.on_surface

    @on_surface.setter
    def on_surface(self, value: dict[str, bool]) -> None:
        self._movement.on_surface = value

    def _handle_death(self) -> None:
        """Entity-level cleanup triggered when health reaches zero."""
        self.combat.reset()

    def die(self) -> None:
        """Mark the entity as dead and clear transient offensive state."""
        self.vitals.is_dead = True
        self._handle_death()

    @property
    def pushbox(self) -> pygame.FRect:
        """Physical collider: walls, floors, separation, platform carry (P2)."""
        return self._pushbox

    @property
    def hitbox(self) -> pygame.FRect:
        """Legacy alias over the pushbox (P2 migration: no caller migrated)."""
        return self._pushbox

    @hitbox.setter
    def hitbox(self, value: pygame.FRect) -> None:
        """Rebind the alias target (test doubles and protocol compat only)."""
        self._pushbox = value

    @property
    def hurtbox(self) -> pygame.FRect:
        """Damage-receiving area: the single zone in legacy configuration."""
        if not self._hurtbox_rects:
            return self._hurtbox_union
        return self._hurtbox_rects[0]

    @property
    def hurtboxes(self) -> tuple[pygame.FRect, ...]:
        """Every damage-receiving zone (single legacy zone by default)."""
        return tuple(self._hurtbox_rects)

    @property
    def hurtbox_tags(self) -> tuple[tuple[str, ...], ...]:
        """Per-zone reserved invulnerability tags (parallel to ``hurtboxes``)."""
        return tuple(zone.tags for zone in self._zones)

    @property
    def hurtbox_mult(self) -> tuple[float, ...]:
        """Per-zone localized damage multiplier (parallel to ``hurtboxes``)."""
        return tuple(zone.mult for zone in self._zones)

    def capture_sweep_origin(self) -> None:
        """Freeze the current zones as the next tick's sweep origin (P1/D3).

        Called once per tick by the gameplay loop, before any movement.
        """
        self._prev_hurtboxes = tuple(rect.copy() for rect in self._hurtbox_rects)

    def swept_hurtboxes(self) -> tuple[pygame.FRect, ...]:
        """Per-zone swept rectangles for the current tick (P1, D1/D4).

        Bilateral-generous by design: a target that dodges more than
        ``SWEEP_MIN_DISPLACEMENT_PX`` but less than
        ``SWEEP_MAX_DISPLACEMENT_PX`` stays hittable for one tick.
        """
        return tuple(
            swept_box(
                self._prev_hurtboxes[index] if index < len(self._prev_hurtboxes) else None,
                rect,
            )
            for index, rect in enumerate(self._hurtbox_rects)
        )

    def swept_hurtbox(self) -> pygame.FRect:
        """Union of the per-zone swept rectangles (legacy single-view API)."""
        zones = self.swept_hurtboxes()
        if not zones:
            return self._hurtbox_union.copy()
        union = zones[0].copy()
        for zone in zones[1:]:
            union = union.union(zone)
        return union

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
        """Derive sprite rect and every hurtbox zone from the pushbox.

        The single derivation point of the hurt geometry (P2): the dash
        squish mutates the pushbox, this re-derives zones — including the
        cached union backing the legacy ``hurtbox`` view.
        """
        self.rect.midbottom = self._pushbox.midbottom
        while len(self._hurtbox_rects) < len(self._zones):
            self._hurtbox_rects.append(pygame.FRect(0, 0, 0, 0))
        while len(self._hurtbox_rects) > len(self._zones):
            self._hurtbox_rects.pop()
        for rect, zone in zip(self._hurtbox_rects, self._zones, strict=True):
            inflate_x, inflate_y = zone.inflate
            rect.size = (
                self._pushbox.width + inflate_x,
                self._pushbox.height + inflate_y,
            )
            rect.center = self._pushbox.center
        self._hurtbox_union = self._hurtbox_rects[0].unionall(
            self._hurtbox_rects[1:]
        ) if len(self._hurtbox_rects) > 1 else self._hurtbox_rects[0].copy()

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

    def turn_around(self) -> None:
        """Face the opposite direction (void avoidance, AI turns)."""
        self.facing_right = not self.facing_right

    def _walk_direction(self) -> float:
        """Signed walk direction: the locomotion axis leads, facing follows.

        Locomotion states set ``move_axis`` before probing, so a stale
        facing never steers a directional query.
        """
        if self.move_axis > 0.0:
            return 1.0
        if self.move_axis < 0.0:
            return -1.0
        return 1.0 if self.facing_right else -1.0

    def is_at_ledge(self) -> bool:
        """Return True when grounded with no ground ahead of the walk.

        A probe hangs off the front foot (``Ledge.PROBE_AHEAD_PX`` wide,
        ``Ledge.PROBE_DROP_PX`` deep): any collider inside means ground,
        nothing inside means void. The walk direction leads (locomotion
        states set ``move_axis`` before probing); facing is only the idle
        fallback. Airborne entities are falling, not at a ledge.
        Deterministic (no randomness); shared by every entity, only the
        enemy AI acts on it.
        """
        if not self.on_surface.get("floor", False):
            return False
        ahead_right = self._walk_direction() > 0.0
        ahead = Ledge.PROBE_AHEAD_PX
        skin = Ledge.PROBE_SKIN_PX
        drop = Ledge.PROBE_DROP_PX
        if ahead_right:
            probe = pygame.FRect(self.hitbox.right, self.hitbox.bottom - skin, ahead, skin + drop)
        else:
            probe = pygame.FRect(
                self.hitbox.left - ahead, self.hitbox.bottom - skin, ahead, skin + drop
            )
        nearby = get_nearby_sprites(
            self,
            spatial_hash=self.spatial_hash,
            collision_sprites=self.collision_sprites,
        )
        for sprite in nearby:
            box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
            if box is not None and probe.colliderect(box):
                return False
        return True

    def find_landing_ahead(
        self, max_dist: float, max_rise: float, max_drop: float
    ) -> tuple[float, float] | None:
        """Next landable ground ahead: (distance from the front foot, drop).

        Samples forward in ``GAP_SCAN_STEP_PX`` increments: the first
        collider whose top sits between ``max_rise`` above and ``max_drop``
        below the feet wins, and its depth below the feet is returned
        alongside the distance. Walls (tops out of band) never match.
        Returns None past ``max_dist``. Deterministic; shared by every
        entity.
        """
        if max_dist <= 0.0:
            return None
        direction = self._walk_direction()
        front = self.hitbox.right if direction > 0.0 else self.hitbox.left
        boxes: list[Any] = []
        for sprite in get_nearby_sprites(
            self,
            spatial_hash=self.spatial_hash,
            collision_sprites=self.collision_sprites,
        ):
            box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
            if box is not None:
                boxes.append(box)
        step = EnemyJump.GAP_SCAN_STEP_PX
        distance = max(step, Ledge.PROBE_AHEAD_PX + step)
        while distance <= max_dist:
            center = front + direction * distance
            sample = pygame.FRect(
                center - 2.0, self.hitbox.bottom - max_rise, 4.0, max_rise + max_drop
            )
            for box in boxes:
                if (
                    sample.colliderect(box)
                    and box.top >= self.hitbox.bottom - max_rise
                    and box.top <= self.hitbox.bottom + max_drop
                ):
                    return distance, box.top - self.hitbox.bottom
            distance += step
        return None

    def is_wall_sliding(self) -> bool:
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
        self._movement.apply_gravity(delta_time)

    def apply_horizontal_movement(self, delta_time: float) -> None:
        """Apply horizontal acceleration and control based on move_axis."""
        self._movement.apply_horizontal_movement(delta_time)

    def check_contact(self) -> None:
        """Update surface contact flags."""
        self._movement.check_contact()

    def handle_collisions(self, axis: Literal["horizontal", "vertical"]) -> None:
        """Resolve collisions along a given axis."""
        self._movement.handle_collisions(axis)

    def move(self, delta_time: float, apply_gravity: bool = True) -> None:
        """Move the entity based on velocity, resolving collisions."""
        self._movement.move(delta_time, apply_gravity=apply_gravity)

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        """Carry the entity along moving platforms."""
        self._movement.apply_moving_platform(moving_platforms)

    def reset_position(self) -> None:
        """Reset the entity to its spawn position and clear all states.

        This method resets position, velocity, health, and various timers.
        It also changes the state machine to idle state if available.
        """
        self.hitbox.center = self.spawn_pos
        self.sync_rects()
        self._movement.stop()
        self.old_hitbox = self.hitbox.copy()
        self.vitals.reset()
        # P1 (D4) / P2: respawn/teleport is a discontinuity — no swept smear.
        self._prev_hurtboxes = ()

        self.combat.reset()

        if hasattr(self.state_machine, "change_state"):
            self.state_machine.change_state("idle", force=True)

        self._on_reset()

    def _on_reset(self) -> None:
        """Hook for subclasses to reset their specific state."""
        pass

    def _can_receive_damage(self) -> bool:
        """Check if the entity can currently receive damage. Override to add immunities."""
        return self.vitals.can_receive_damage()

    @property
    def is_invincible(self) -> bool:
        """Whether the entity is currently invincible (e.g., dashing, hurt, knockback)."""
        state_machine = getattr(self, "state_machine", None)
        if state_machine is None:
            return False
        return bool(state_machine.has_tag("invincible"))

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
        return self.vitals.apply_damage(amount)

    @property
    def reaction_status(self) -> ReactionStatus | None:
        """The last hit-reaction cause (what hit, how hard, which way).

        Owned by ``ReactionComponent``; the state machine owns the category in
        progress. Render/debug reads only — never snapshotted.
        """
        return self._reaction.status

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
        self._reaction.apply_knockback(knockback, source_center_x)

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
        return self._reaction.handle_heavy_knockback(knockback, source_center_x)

    def receive_damage(
        self,
        amount: float,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
        unblockable: bool = False,
        height: str = "mid",
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
        unblockable : bool
            Accepted for protocol compatibility; base entity has no guard.
        height : str
            Accepted for protocol compatibility; base entity has no guard.

        Returns
        -------
        DamageResult
            A dataclass detailing the outcome of the damage application.
        """
        if not self._can_receive_damage():
            return DamageResult()

        actual_damage = self._apply_damage(amount)

        if actual_damage > 0:
            self.flash_timer = HitFlash.DURATION

        if actual_damage > 0 and knockback is not None:
            self._apply_knockback(knockback, source_center_x)

        self.vitals.set_invincibility()

        heavy_knockback = False
        if interrupt and not self.is_dead and actual_damage > 0 and knockback is not None:
            heavy_knockback = self._handle_heavy_knockback(knockback, source_center_x)

        return DamageResult(
            applied=actual_damage > 0,
            killed=self.is_dead,
            actual_damage=actual_damage,
            heavy_knockback=heavy_knockback,
        )

    def stagger(self, duration: float) -> None:
        """Apply stagger, handling super armor and stunlock protection.

        Super armor is consumed after ``SUPER_ARMOR_THRESHOLD`` hits.
        If the entity has super armor and the threshold is not reached,
        no stagger is applied.

        Parameters
        ----------
        duration : float
            The duration of the stagger in seconds.
        """
        self._reaction.stagger(duration)

    def set_juggle(self, gravity_mult: float, duration: float) -> None:
        """Float or slam an airborne victim for ``duration`` (Phase 5 #4)."""
        self.gravity_scale = gravity_mult
        self.juggle_timer = max(0.0, duration)

    def _tick_juggle(self, delta_time: float, was_grounded: bool) -> None:
        """Decay juggle/OTG timers; landing from a juggle grants OTG guard."""
        if self.juggle_timer > 0.0:
            self.juggle_timer -= delta_time
            if self.juggle_timer <= 0.0:
                self.juggle_timer = 0.0
                self.gravity_scale = 1.0
        if self.otg_timer > 0.0:
            self.otg_timer = max(0.0, self.otg_timer - delta_time)
        now_grounded = bool(self.on_surface.get("floor", False))
        if now_grounded and not was_grounded:
            self.gravity_scale = 1.0
            self.juggle_timer = 0.0
            if self.stagger_timer > 0.0 or self.combat.is_hurt:
                self.otg_timer = CombatSettings.OTG_INVULN_DURATION

    def _pre_update(self, delta_time: float) -> None:
        """Hook called at the beginning of the update loop, before combat and physics."""
        pass

    def _animation_name(self) -> str | None:
        """Animation key matching the current state, or None to keep it.

        Override in subclasses that attach an :class:`Animator`; returning
        None lets the current animation keep playing (e.g. states without
        dedicated art reuse the last shown animation).
        """
        return None

    def _update_animator(self, delta_time: float) -> None:
        """Tick the optional animator and publish its surface as ``image``.

        The display surface is scaled to the sprite rect so the physics
        rect stays authoritative (audit F2.2); entities without an
        animator keep their flat colored surface.
        """
        if self.animator is None:
            return
        name = self._animation_name()
        if name is not None:
            self.animator.play(name)
        self.animator.update(delta_time)
        surface = self.animator.surface(
            (round(self.rect.width), round(self.rect.height)),
            self.facing_right,
        )
        if surface is not None:
            self.image = surface

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
        self.vitals.tick_timers(delta_time)
        if self.flash_timer > 0.0:
            self.flash_timer = max(0.0, self.flash_timer - delta_time)
        if self.reaction_age > 0.0:
            self.reaction_age = max(0.0, self.reaction_age - delta_time)

        self._pre_update(delta_time)
        self._update_state_machine(delta_time)
        self.combat.update(delta_time)
        was_grounded = bool(self.on_surface.get("floor", False))
        fall_speed = float(self.velocity.y)
        self.move(delta_time, apply_gravity=True)
        now_grounded = bool(self.on_surface.get("floor", False))
        # Landing edge with the pre-move fall speed: hard landings become
        # dust puffs in PhysicsSystem; anything else zeroes the hint.
        self.landed_impact = fall_speed if now_grounded and not was_grounded else 0.0
        self._tick_juggle(delta_time, was_grounded)
        self.combat.sync_attack_box()
        self._post_update(delta_time)
        self._update_animator(delta_time)

    def save_state(self) -> EntitySnapshot:
        """Capture the full simulation state for rollback (Phase 3 #3).

        ``rng`` is captured so any entity that consumes randomness during a
        tick stays bit-identical across a rollback.  Subclasses (``Player``)
        extend ``extra`` with their own controllers' runtime state.
        """
        snap = EntitySnapshot(
            entity=self,
            entity_id=self.id,
            hitbox=(self.hitbox.x, self.hitbox.y, self.hitbox.width, self.hitbox.height),
            old_hitbox=(
                self.old_hitbox.x,
                self.old_hitbox.y,
                self.old_hitbox.width,
                self.old_hitbox.height,
            ),
            velocity=(self.velocity.x, self.velocity.y),
            on_surface=dict(self.on_surface),
            facing_right=self.facing_right,
            move_axis=self.move_axis,
            pushable=self.pushable,
            rng_state=self.rng.getstate(),
            vitals=self.vitals.save_state(),
            combat=self.combat.save_state(),
            state_machine=self.state_machine.save_state(),
        )
        snap.groups = list(self.groups())
        snap.extra = {
            "gravity_scale": self.gravity_scale,
            "juggle_timer": self.juggle_timer,
            "otg_timer": self.otg_timer,
            "parries_given": self.parries_given,
            "parries_taken": self.parries_taken,
            "parry_stun_threshold": self.parry_stun_threshold,
            "parry_stun_duration": self.parry_stun_duration,
        }
        return snap

    def load_state(self, snapshot: EntitySnapshot) -> None:
        """Restore the full simulation state from a rollback snapshot.

        Geometry is written to the live ``hitbox``/``old_hitbox`` objects and
        ``sync_rects`` re-derives ``rect``/``hurtbox``; ``velocity`` and
        ``on_surface`` route through their delegating properties into the
        movement component.
        """
        self.hitbox.x, self.hitbox.y, self.hitbox.width, self.hitbox.height = snapshot.hitbox
        self.old_hitbox.x, self.old_hitbox.y, self.old_hitbox.width, self.old_hitbox.height = (
            snapshot.old_hitbox
        )
        self.sync_rects()
        # P1 (D3) / P2: ``prev`` is re-derived at the next frontier capture;
        # no snapshot field carries it across a rollback.
        self._prev_hurtboxes = ()
        self.velocity = Vector2(snapshot.velocity)
        self.on_surface = dict(snapshot.on_surface)
        self.facing_right = snapshot.facing_right
        self.move_axis = snapshot.move_axis
        self.pushable = snapshot.pushable
        self.rng.setstate(snapshot.rng_state)
        self.vitals.load_state(snapshot.vitals)
        self.combat.load_state(snapshot.combat)
        self.state_machine.load_state(snapshot.state_machine)
        extra = snapshot.extra or {}
        self.gravity_scale = float(extra.get("gravity_scale", 1.0))
        self.juggle_timer = float(extra.get("juggle_timer", 0.0))
        self.otg_timer = float(extra.get("otg_timer", 0.0))
        self.parries_given = int(extra.get("parries_given", 0))
        self.parries_taken = int(extra.get("parries_taken", 0))
        self.parry_stun_threshold = (
            int(extra["parry_stun_threshold"])
            if extra.get("parry_stun_threshold") is not None
            else None
        )
        self.parry_stun_duration = float(extra.get("parry_stun_duration", 0.0))
