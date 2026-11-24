"""Base module for game entities with physics, health, and combat capabilities."""

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import pygame
from pygame.math import Vector2
from pygame.sprite import Group

from src.combat.attack_loading import load_attacks
from src.combat.combat_component import CombatComponent, CombatSnapshot, NullCombatComponent
from src.combat.combatant_protocol import Combatant, DamageResult, Finish
from src.combat.damage_types import DamageType
from src.combat.frame_data import AttackDefinition, Height, MoveId, Stance
from src.combat.knockback import KnockbackConfig
from src.combat.shapes import ShapeKind, ShapePose, SweptShape
from src.combat.sweep import swept_box
from src.core.animation.animator import Animator
from src.core.ecs.combat_table import CombatTable
from src.core.ecs.geometry_table import GeometryTable
from src.core.ecs.movement_table import MovementTable
from src.core.ecs.presentation import PresentationSprite
from src.core.ecs.vitals_table import VitalsTable
from src.core.rendering.render_hints import RenderHints
from src.core.settings import Clash as ClashSettings
from src.core.settings import Combat as CombatSettings
from src.core.settings import (
    HitFlash,
    Locomotion,
    Physics,
    Turn,
    resolve_turn_profile,
)
from src.core.settings import Stun as StunSettings
from src.core.sprite_groups import SpriteGroups
from src.entities.components.animation_publisher import AnimationPublisher
from src.entities.components.doom import DoomTracker
from src.entities.components.environment import EnvironmentScanner
from src.entities.components.movement import MovementComponent
from src.entities.components.reaction import (
    ReactionComponent,
    ReactionStatus,
)
from src.entities.hurtbox_zones import HurtboxZoneDef
from src.entities.id_factory import IdFactory, shared_id_factory
from src.entities.player_controllers import DashController
from src.entities.vitals import Vitals, VitalsSnapshot
from src.physics import (
    SpatialHash,
    apply_horizontal_movement,
    apply_moving_platform,
    move_entity,
    resolve_collisions,
)
from src.physics.collisions import CollisionSprite
from src.physics.movement import WallJumpLock
from src.states import state_names
from src.states.null_state_machine import NullStateMachine
from src.states.state_machine import StateMachine, StateMachineSnapshot
from src.states.turn_state import FACING_LOCKED

__all__ = ["Entity"]


@dataclass
class EntitySnapshot:
    """Serializable capture of an entity's full simulation state.

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


class Entity:
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

    # A fighter always has a picture; ``Sprite`` alone allows none.
    image: pygame.Surface

    # Only a fighter that can dash has the resource; the player sets it. Declared
    # here so the systems that walk every entity ask ``is None`` and not ``getattr``.
    dash: DashController | None = None

    # Dense kinematic row, bound by ``SpriteGroups.add_fighter`` for fighters
    # that live in a level. A standalone entity in a test keeps the component.
    movement_table: MovementTable | None = None
    movement_slot: int | None = None
    vitals_table: VitalsTable | None = None
    geometry_table: GeometryTable | None = None
    geometry_slot: int | None = None
    combat_table: CombatTable | None = None
    combat_slot: int | None = None
    presentation: PresentationSprite | None = None
    sprite_groups: SpriteGroups | None = None

    # Only the player drives attack poses off frame data. Declared here so the
    # animation publisher reads a declared field on every fighter instead of
    # tolerating a missing one with getattr.
    _phase_driven_attack_art: bool = False

    # The dark step is a player resource, but the FX pass samples every fighter
    # for it. Declared on the base so the read needs no getattr tolerance.
    rush_timer: float = 0.0

    # The fighters this one shares a level with, filed by
    # ``SpriteGroups.add_fighter``. Empty for a fighter built on its own.
    roster: Iterable[Entity] = ()

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
        attacks: Mapping[MoveId, AttackDefinition] | None = None,
        hurt_duration: float | None = None,
        invincibility_duration: float = 0.0,
        rng: random.Random | None = None,
        entity_id: str | None = None,
        spatial_hash: SpatialHash | None = None,
        id_factory: IdFactory | None = None,
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
        attacks : Mapping[MoveId, AttackDefinition] | None
            Dictionary of attack definitions to load into the combat component.
        hurt_duration : float | None
            Duration of the hurt state. Defaults to standard combat settings.
        invincibility_duration : float
            Duration of invincibility frames after taking damage.
        rng : random.Random | None
            Optional random number generator instance for deterministic behaviors.
        spatial_hash : SpatialHash | None
            Shared collision grid covering ``collision_sprites``. Passed in
            rather than assigned after construction because the fallback in
            :func:`get_nearby_sprites` is an O(n) scan of every collidable in
            the level, and a level that forgets to hand the grid over pays a
            measured x2.4 on the whole simulation with no visible symptom.
        """
        # The sprite *proxy* is what pygame groups hold; the simulation
        # itself is a plain object backed by dense tables.
        factory = id_factory if id_factory is not None else shared_id_factory()
        self.id: str = entity_id if entity_id is not None else factory.entity_id()
        self.pushable: bool = True
        self.faction: str = faction
        self.rng = rng or random.Random()

        self.image = pygame.Surface(size)
        self.image.fill(color)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.presentation = PresentationSprite(self, *groups)
        self._init_boxes(hitbox_inflate, hurtbox_inflate, hurtbox_zones)

        self.collision_sprites: Iterable[CollisionSprite] = cast(
            Iterable[CollisionSprite], collision_sprites
        )
        # Injected at construction: without it ``move_entity`` falls back to a
        # linear scan of every collider (correct, measured 2.4x slower).
        self.spatial_hash: SpatialHash | None = spatial_hash
        # Owns velocity and surface contacts, exposed by the properties below.
        self._movement = MovementComponent(self)
        self.moving_platforms: Iterable[Any] = []
        # The lock that damps the run after a wall jump; only the player has one.
        self.wall_jump_lock: WallJumpLock | None = None

        self._init_motion()
        self._init_combat_state()
        self._init_turn_tuning()
        self._init_render_hints()

        self.vitals = Vitals(
            health=health,
            max_health=max_health,
            invincibility_duration=invincibility_duration,
            spawn_pos=Vector2(spawn_pos if spawn_pos is not None else pos),
            on_death=self._handle_death,
        )
        if combat is not None:
            self._combat: CombatComponent | NullCombatComponent = combat
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
        # Built after vitals and combat: a reaction drives both.
        self._reaction = ReactionComponent(self)
        # Pure ground probes, kept out of the tick template and combat facade.
        self._environment = EnvironmentScanner(self)
        # Animation is presentation: its publisher never feeds a game rule.
        self._animation_publisher = AnimationPublisher(self)
        # Doom/finisher transition rules, kept out of the combatant facade.
        self._doom = DoomTracker(self)  # type: ignore[arg-type]
        # Subclasses attach an Animator; without one the flat surface is drawn.
        self.animator: Animator | None = None

    def _init_boxes(
        self,
        hitbox_inflate: Sequence[float],
        hurtbox_inflate: Sequence[float],
        hurtbox_zones: Sequence[HurtboxZoneDef] | None,
    ) -> None:
        """The pushbox (public name ``hitbox``), the hurtbox zones and the sweep origins.

        The zones derive from the pushbox in :meth:`sync_rects`, the single
        derivation point; no zone config means one zone, the legacy hurtbox.
        The sweep origins are written by :meth:`capture_sweep_origin` and reset
        on a teleport or a rollback.
        """
        self._pushbox = self.rect.inflate(*hitbox_inflate)
        self._pushbox.midbottom = self.rect.midbottom
        self.old_hitbox = self._pushbox.copy()
        self._hurtbox_inflate: tuple[float, float] = (
            float(hurtbox_inflate[0]),
            float(hurtbox_inflate[1]),
        )
        self._zones: tuple[HurtboxZoneDef, ...] = (
            tuple(hurtbox_zones)
            if hurtbox_zones is not None
            else (HurtboxZoneDef(inflate=self._hurtbox_inflate),)
        )
        self._hurtbox_rects: list[pygame.FRect] = []
        self._hurtbox_union: pygame.FRect = pygame.FRect(0, 0, 0, 0)
        self._sync_signature: tuple[float, float, float, float, tuple[float, float], int] | None = (
            None
        )
        self._prev_hurtboxes: tuple[pygame.FRect, ...] = ()
        self._prev_pushbox: pygame.FRect | None = None
        self.contact_shape: ShapePose = ShapePose(
            ShapeKind.AABB, self._pushbox.size, self._pushbox.center
        )
        self._previous_contact_shape: ShapePose | None = None
        self.sync_rects()

    def _init_motion(self) -> None:
        """Movement and gravity tuning, per fighter, defaulting to :class:`Physics`."""
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
        # Gravity multiplier while juggled; fast fall from the down action.
        self.gravity_scale: float = 1.0
        # How much a hit moves this fighter: every knockback it takes is
        # divided by it (``ReactionComponent``). Tuning, set from the config.
        self.weight: float = 1.0
        self.fast_fall: bool = False
        # Physics robustness: the bounded resolver flags a crush, and the
        # pre-carry backup lets it be reverted.
        self.crushed: bool = False
        self.carry_backup: tuple[float, float, float, float] | None = None

    def _init_combat_state(self) -> None:
        """Juggle and off-the-ground timers, and the stun gauge."""
        self.juggle_timer: float = 0.0
        self.otg_timer: float = 0.0
        # How long landing from a launch protects this fighter from ground hits.
        self.otg_guard_duration: float = CombatSettings.OTG_INVULN_DURATION
        self.parries_given: int = 0
        # The stun gauge: blows and parried attacks fill it, and a full one
        # stuns the fighter for ``stun_duration``. ``stun_max`` is the size of
        # the gauge, copied from the config on spawn; None is never stunned.
        self.stun: float = 0.0
        self.stun_max: float | None = None
        self.stun_duration: float = 0.0
        self.stun_decay_delay: float = 0.0
        # Where a fighter stood when it began a dodge that can still be a
        # dark step; only the player dodges.
        self.dodge_ghost: pygame.FRect | None = None
        # Whether a blow that would kill this fighter leaves it doomed instead,
        # waiting for the death blow. Set by the fighters that can be doomed.
        self.doomable: bool = False

    def _init_turn_tuning(self) -> None:
        """The turn-around pivot: off by default, tuned per fighter.

        The knobs mirror :class:`settings.Turn` as defaults, not as authority, so
        a goblin and a boss can turn differently. The flag gates the brake as
        well as the hold: gating the hold alone would change how enemies stop.
        """
        self.turn_profile: str = "default"
        self.turn_enabled: bool = False
        self.turn_delay_s: float = Turn.DELAY_S
        self.turn_brake_control: float = Turn.BRAKE_CONTROL
        self.turn_plant_px_s: float = Turn.PLANT_PX_S
        self.turn_min_speed_px_s: float = Turn.MIN_SPEED_PX_S
        self.turn_lead_px: float = Turn.LEAD_PX
        self.turn_skew_px: float = Turn.SKEW_PX

    def _init_render_hints(self) -> None:
        """State the drawing reads and the simulation never does: never snapshotted.

        Kept on the entity so the renderer reads a sprite and not its state
        machine, and in one object so what a rollback skips is a type.
        """
        self.render_hints: RenderHints = RenderHints()

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
    def stance(self) -> Stance:
        """The posture this entity is in, which decides which moves are live.

        Ground or air, from floor contact. No crouch and no wall slide: those
        belong to the player, which overrides this. An entity that is not on the
        floor is airborne whether or not it was ever meant to leave it -- a
        goblin knocked off a ledge is in the air, and reading that as ground
        would let it throw ground moves at the moment it can least afford to.

        Defined here rather than only on the player so the attack policy can ask
        any combatant without a type check.
        """
        return Stance.GROUND if self.on_surface.get("floor", False) else Stance.AIR

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
    # Kinematic state lives in the level's dense movement table for fighters
    # that have one. Each entity owns a stable view, so the hundreds of
    # in-place writes in ``src.physics`` and the state machines keep working;
    # standalone entities still delegate to their MovementComponent.
    # ------------------------------------------------------------------

    def ensure_presentation(self, groups: SpriteGroups) -> None:
        """Create or re-attach the draw proxy for this fighter."""
        if self.presentation is None:
            self.presentation = PresentationSprite(self)
        proxy = self.presentation
        if proxy not in groups.presentation_sprites:
            groups.presentation_sprites.add(proxy)

    def bind_movement(self, table: MovementTable) -> None:
        """Attach this fighter to a level's kinematic table, once."""
        if self.movement_table is table:
            return
        if self.movement_table is not None and self.movement_slot is not None:
            self.movement_table.release(self.movement_slot)
        self.movement_table = table
        self.movement_slot = table.register(self)

    def bind_vitals(self, table: VitalsTable) -> None:
        """Attach this fighter's vitals to a level's dense table, once."""
        if self.vitals_table is table:
            return
        self.vitals_table = table
        self.vitals.bind(table)

    def bind_geometry(self, table: GeometryTable) -> None:
        """Attach this fighter's pushbox to a level's dense table, once."""
        if self.geometry_table is table:
            return
        if self.geometry_table is not None and self.geometry_slot is not None:
            self.geometry_table.release(self.geometry_slot)
        self.geometry_table = table
        self.geometry_slot = table.register(self)

    def bind_combat(self, table: CombatTable) -> None:
        """Attach this fighter's combat component to a level's dense table."""
        if self.combat_table is table:
            return
        if self.combat_table is not None and self.combat_slot is not None:
            self.combat_table.release(self.combat_slot)
        self.combat_table = table
        self.combat_slot = table.register(self)

    @property
    def combat(self) -> CombatComponent | NullCombatComponent:
        """The combat component, owned by the dense row when bound."""
        if self.combat_table is not None and self.combat_slot is not None:
            component: CombatComponent | NullCombatComponent = self.combat_table.combat_of(
                self.combat_slot
            )
            return component
        return self._combat

    @combat.setter
    def combat(self, value: CombatComponent | NullCombatComponent) -> None:
        if self.combat_table is not None and self.combat_slot is not None:
            self.combat_table.column("combat")[self.combat_slot] = value
        else:
            self._combat = value

    @property
    def velocity(self) -> Vector2:
        """Current velocity, backed by the dense row when bound to a level."""
        if self.movement_table is not None and self.movement_slot is not None:
            view, _ = self.movement_table.views_for(self.movement_slot)
            return cast(Vector2, view)
        return self._movement.velocity

    @velocity.setter
    def velocity(self, value: Vector2) -> None:
        if self.movement_table is not None and self.movement_slot is not None:
            view, _ = self.movement_table.views_for(self.movement_slot)
            view.update(value.x, value.y)
            return
        self._movement.velocity = value

    @property
    def on_surface(self) -> dict[str, bool]:
        """Contact flags, backed by the dense row when bound to a level."""
        if self.movement_table is not None and self.movement_slot is not None:
            _, view = self.movement_table.views_for(self.movement_slot)
            return cast(dict[str, bool], view)
        return self._movement.on_surface

    @on_surface.setter
    def on_surface(self, value: dict[str, bool]) -> None:
        if self.movement_table is not None and self.movement_slot is not None:
            _, view = self.movement_table.views_for(self.movement_slot)
            for flag in ("floor", "left", "right"):
                view[flag] = value.get(flag, False)
            return
        self._movement.on_surface = value

    @property
    def is_dashing(self) -> bool:
        return self.state_machine.current_state_name == state_names.DASH

    def wall_bounce_factor(self) -> float:
        """How much horizontal velocity a wall returns, 0 outside knockback.

        The collision resolver asks the entity instead of importing the state
        vocabulary and the combat tuning, keeping physics independent of both.
        """
        if self.state_machine.current_state_name == state_names.KNOCKBACK:
            return CombatSettings.WALL_BOUNCE_FACTOR
        return 0.0

    def _handle_death(self) -> None:
        """Entity-level cleanup triggered when health reaches zero."""
        self.combat.reset()

    def die(self) -> None:
        """Mark the entity as dead and clear transient offensive state."""
        self.vitals.is_dead = True
        self._handle_death()

    @property
    def hitbox(self) -> pygame.FRect:
        """The physical collider: walls, floors, separation, platform carry.

        ``pushbox`` is the name the same FRect had at this tier and is kept for
        the *derived* forms -- ``swept_pushbox`` and the overlay legend's
        "blue/red pushbox". The undelayed collider itself is spelled ``hitbox``
        everywhere in ``src``, and the multi-hurtbox zones are derived from it
        (see ``sync_rects``).
        """
        if self.geometry_table is not None and self.geometry_slot is not None:
            return self.geometry_table.hitbox_of(self.geometry_slot)
        return self._pushbox

    @hitbox.setter
    def hitbox(self, value: pygame.FRect) -> None:
        """Rebind the collider, including the dense row when bound."""
        if self.geometry_table is not None and self.geometry_slot is not None:
            self.geometry_table.column("hitbox")[self.geometry_slot] = value
        else:
            self._pushbox = value

    @property
    def hurtbox(self) -> pygame.FRect:
        """Damage-receiving area: union of every zone.

        Legacy single-zone configurations are exactly that one zone, so the
        union view stays byte-identical to the pre-P2 ``hurtbox``.
        """
        return self._hurtbox_union

    @property
    def hurtboxes(self) -> tuple[pygame.FRect, ...]:
        """Every damage-receiving zone (single legacy zone by default)."""
        return tuple(self._hurtbox_rects)

    @property
    def hurtbox_tags(self) -> tuple[tuple[str, ...], ...]:
        """Per-zone invulnerability tags, including active state tags."""
        airborne = not self.on_surface.get("floor", False)
        return tuple(
            zone.tags + (("airborne",) if airborne and "airborne" in zone.invuln_states else ())
            for zone in self._zones
        )

    @property
    def hurtbox_mult(self) -> tuple[float, ...]:
        """Per-zone localized damage multiplier (parallel to ``hurtboxes``)."""
        return tuple(zone.mult for zone in self._zones)

    @property
    def hurtbox_zone_names(self) -> tuple[str, ...]:
        """Per-zone debug names (parallel to ``hurtboxes``; ``""`` when unnamed)."""
        return tuple(zone.name for zone in self._zones)

    def capture_sweep_origin(self) -> None:
        """Freeze the current zones as the next tick's sweep origin.

        Called once per tick by the gameplay loop, before any movement.
        """
        self._prev_hurtboxes = tuple(rect.copy() for rect in self._hurtbox_rects)
        self._prev_pushbox = self._pushbox.copy()
        self._previous_contact_shape = self.contact_shape

    def swept_pushbox(self) -> pygame.FRect:
        """Return the physical pushbox swept over the current tick."""
        return swept_box(self._prev_pushbox, self._pushbox)

    def swept_contact_shapes(self) -> tuple[SweptShape, ...]:
        return (SweptShape(self._previous_contact_shape, self.contact_shape),)

    def swept_hurtboxes(self) -> tuple[pygame.FRect, ...]:
        """Per-zone swept rectangles for the current tick.

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

    @property
    def is_stunned(self) -> bool:
        """Whether the fighter is stunned: helpless, and open to a throw."""
        return bool(self.state_machine.current_state_name == state_names.DIZZY)

    @property
    def is_downed(self) -> bool:
        """Whether the fighter lies on the ground after a launch."""
        return bool(self.state_machine.current_state_name == state_names.DOWNED)

    @property
    def is_doomed(self) -> bool:
        """Whether the fighter waits for the death blow; see :class:`DoomTracker`."""
        return self._doom.is_doomed

    @property
    def is_helpless(self) -> bool:
        """Stunned, downed or doomed; see :class:`DoomTracker`."""
        return self._doom.is_helpless

    def doom(self) -> None:
        """Enter the doomed state; see :class:`DoomTracker`."""
        self._doom.doom()

    def recover_from_doom(self) -> None:
        """Get up after a missed death blow; see :class:`DoomTracker`."""
        self._doom.recover_from_doom()

    @property
    def finish(self) -> Finish:
        """What this fighter's blow does to a target it would kill."""
        return self._doom.finish

    def guards_against(self, height: Height, unblockable: bool, source_center_x: float) -> bool:
        """Whether this fighter's guard stops the hit. No guard by default."""
        del height, unblockable, source_center_x
        return False

    def on_clash(self, other: Combatant) -> None:
        """This fighter's attack and ``other``'s cancelled each other. Nothing by default."""
        del other

    @property
    def counter_covered(self) -> bool:
        """Whether this fighter is striking back behind its guard. Never by default."""
        return False

    def on_deflected(self, source_center_x: float) -> None:
        """This fighter's blow was stopped by a guard. Nothing by default."""
        del source_center_x

    def lose_lock(self) -> None:
        """This fighter lost a blade lock: thrown off balance, open but not stunned."""
        self.combat.cancel_attack()
        self.stagger(ClashSettings.WIN_STAGGER)

    def add_stun(self, amount: float) -> bool:
        """Fill the stun gauge by ``amount``; True if that stunned the fighter.

        A fighter with no gauge, one already stunned and a dead one take none.
        The stun ends whatever the fighter was doing, an armoured attack
        included.
        """
        if self.stun_max is None or amount <= 0.0 or self.is_dead or self.is_helpless:
            return False
        self.stun += amount
        self.stun_decay_delay = StunSettings.DECAY_DELAY
        if self.stun < self.stun_max:
            return False
        self.stun = 0.0
        self.combat.cancel_attack()
        self.combat.reset_hurt_state()
        self.state_machine.change_state(state_names.DIZZY, force=True, duration=self.stun_duration)
        return True

    def _tick_stun(self, delta_time: float) -> None:
        """Drain the stun gauge once nothing has added to it for a while."""
        if self.stun <= 0.0:
            return
        if self.stun_decay_delay > 0.0:
            self.stun_decay_delay = max(0.0, self.stun_decay_delay - delta_time)
            return
        self.stun = max(0.0, self.stun - StunSettings.DECAY_PER_S * delta_time)

    def on_hit_evaded(self) -> bool:
        """A hit passed through this fighter while invincible, or its ghost. Nothing by default.

        :class:`~src.entities.player.Player` makes a perfect dodge of it.
        """
        return False

    def on_hit_confirmed(
        self, target: Combatant, combo_advanced: bool, result: DamageResult
    ) -> None:
        """One of this fighter's hits took health off ``target``. Nothing by default.

        :class:`~src.entities.player.Player` is paid for it.
        """
        del target, combo_advanced, result

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

        The single derivation point of the hurt geometry: the dash
        squish mutates the pushbox, this re-derives zones — including the
        cached union backing the legacy ``hurtbox`` view.

        ``resolve_collisions`` calls this after *every* sub-step of *both*
        axes, so it is the most-executed method in the simulation. It is
        written to be cheap when it can be: the zone ``FRect``s are already
        in the right list, and the pushbox rarely moves between two
        consecutive calls, so the union and the contact shape are rebuilt
        only when their inputs actually changed. Identical inputs produce an
        identical result either way, so this is a pure short-circuit, not an
        approximation.
        """
        pushbox = self._pushbox
        signature = (
            pushbox.x,
            pushbox.y,
            pushbox.width,
            pushbox.height,
            self.rect.midbottom,
            len(self._zones),
        )
        if signature == self._sync_signature:
            return
        self.rect.midbottom = pushbox.midbottom
        while len(self._hurtbox_rects) < len(self._zones):
            self._hurtbox_rects.append(pygame.FRect(0, 0, 0, 0))
        while len(self._hurtbox_rects) > len(self._zones):
            self._hurtbox_rects.pop()
        for rect, zone in zip(self._hurtbox_rects, self._zones, strict=True):
            inflate_x, inflate_y = zone.inflate
            rect.size = (
                pushbox.width + inflate_x,
                pushbox.height + inflate_y,
            )
            rect.center = (pushbox.centerx, pushbox.centery + zone.offset_y)
        # Only the single-zone layout can be short-circuited, and only by its
        # own rect: with several zones the union depends on all of them, so
        # one of the others moving would leave a stale union behind. The
        # common case is one zone, and this is the common path.
        #
        # The contact shape below is skipped on the same condition, and
        # correctly so: it is derived from the pushbox centre, which is what
        # `only.center` mirrors, so an unchanged zone rect means an unchanged
        # centre and a fresh `ShapePose` would be equal to the one held.
        if len(self._hurtbox_rects) == 1:
            only = self._hurtbox_rects[0]
            unchanged = (
                self._hurtbox_union.size == only.size and self._hurtbox_union.center == only.center
            )
            if not unchanged:
                self._hurtbox_union = only.copy()
        else:
            self._hurtbox_union = (
                self._hurtbox_rects[0].unionall(self._hurtbox_rects[1:])
                if len(self._hurtbox_rects) > 1
                else self._hurtbox_rects[0].copy()
            )
            unchanged = False
        self._sync_signature = (
            pushbox.x,
            pushbox.y,
            pushbox.width,
            pushbox.height,
            self.rect.midbottom,
            len(self._zones),
        )
        if unchanged:
            return
        self.contact_shape = ShapePose(
            self.contact_shape.kind,
            self.contact_shape.size,
            pushbox.center,
            self.contact_shape.angle,
        )

    def apply_turn_profile(self, name: str | None = None) -> None:
        """Adopt the named pivot profile, resolving its inheritance chain.

        The one call that turns a group or a sub-group into per-fighter
        numbers. A fighter class names the group it belongs to in its own
        constructor -- ``"player"``, ``"enemy"`` -- and a type inside a group
        names a sub-group that layers onto it, so "the enemies take it, except
        the slimes" is two lines in :data:`settings.PROFILES` and nothing here
        at all.

        Called from the constructor rather than lazily, because the brake reads
        its rate on the first tick of a reversal: a fighter that resolved its
        profile when it first reversed would be handled one way while running
        right and another while turning, which is the kind of difference that
        only shows up under pressure.

        Anything assigned to a ``turn_*`` attribute after this call wins, so a
        class can still say a number outright -- that is the layer above the
        named profiles, and the reason they are partial.
        """
        resolved = resolve_turn_profile(self.turn_profile if name is None else name)
        self.turn_profile = self.turn_profile if name is None else name
        self.turn_enabled = bool(resolved.enabled)
        self.turn_delay_s = float(resolved.delay_s or 0.0)
        self.turn_brake_control = float(resolved.brake_control or 0.0)
        self.turn_plant_px_s = float(resolved.plant_px_s or 0.0)
        self.turn_min_speed_px_s = float(resolved.min_speed_px_s or 0.0)
        self.turn_lead_px = float(resolved.lead_px or 0.0)
        self.turn_skew_px = float(resolved.skew_px or 0.0)

    def face_movement(self, threshold: float = Locomotion.TURN_DEADZONE) -> None:
        """Orient the entity based on its current movement axis.

        Silent while the state machine says the mirror is held. That tag is how
        a state keeps a facing it has not finished applying: the pivot enters
        with the axis already opposite the facing, and without this the very
        next tick would mirror the sprite and cancel the hold it just asked
        for. Asked as a tag rather than by state name so this base class needs
        to know nothing about the player's states.
        """
        if self.state_machine.has_tag(FACING_LOCKED):
            return
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
        """Whether grounded with no ground ahead; see :class:`EnvironmentScanner`."""
        return self._environment.is_at_ledge()

    def find_landing_ahead(
        self, max_dist: float, max_rise: float, max_drop: float
    ) -> tuple[float, float] | None:
        """Next landable ground ahead; see :class:`EnvironmentScanner`."""
        return self._environment.find_landing_ahead(max_dist, max_rise, max_drop)

    def is_wall_sliding(self) -> bool:
        """Return True if the entity is currently sliding down a wall."""
        return False

    def _on_floor_contact(self) -> None:
        """Called when the entity lands on the floor."""
        pass

    def _on_wall_contact(self) -> None:
        """Called when the entity touches a wall while airborne."""
        pass

    def apply_horizontal_movement(self, delta_time: float) -> None:
        """Apply horizontal acceleration and control based on move_axis."""
        apply_horizontal_movement(self, delta_time)

    def handle_collisions(self, axis: Literal["horizontal", "vertical"]) -> None:
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
        self.vitals.reset()
        # P1 / P2: respawn/teleport is a discontinuity — no swept smear.
        self._prev_hurtboxes = ()
        self._prev_pushbox = None
        self._previous_contact_shape = None

        self.combat.reset()
        self.stun = 0.0
        self.stun_decay_delay = 0.0

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
        """Whether nothing hits the entity now: its state, or the attack it is playing out."""
        if self.state_machine.has_tag("invincible"):
            return True
        attack = self.combat.current_attack_def
        return attack is not None and attack.invincible

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

    def kill(self) -> None:
        """Leave the sprite groups *and* the collision grid.

        ``pygame.sprite.Sprite.kill`` only leaves the groups, and the
        environment hash is not a group -- it is handed the level's collidables
        and queried directly by every entity that moves. So an entity removed
        through the historical API stayed in the grid: no query could find it
        (it is gone, so it cannot be a neighbour) and nothing ever dropped it.

        Today that costs nothing, because nothing that dies is in the
        environment grid: the tiles are static and the spawner-created enemies
        are never added to it. It is the *shape* of the bug that matters. A
        grid that keeps a dead entity alive also keeps the bucket pointing at
        it, and the next entity allocated can be handed the recycled address --
        at which point ``add`` would see a key it already has and skip the
        insertion, and the new entity would pass through everything. See
        :meth:`src.physics.spatial_hash.SpatialHash.add`.
        """
        spatial_hash = self.spatial_hash
        if spatial_hash is not None:
            spatial_hash.remove(self)
        if self.movement_table is not None and self.movement_slot is not None:
            slot = self.movement_slot
            self._movement.velocity.update(
                self.movement_table.column("vx")[slot], self.movement_table.column("vy")[slot]
            )
            for flag in ("floor", "left", "right"):
                self._movement.on_surface[flag] = self.movement_table.column(flag)[slot]
            self.movement_table.release(slot)
            self.movement_slot = None
        if self.geometry_table is not None and self.geometry_slot is not None:
            self._pushbox = self.geometry_table.hitbox_of(self.geometry_slot)
            self.geometry_table.release(self.geometry_slot)
            self.geometry_slot = None
        if self.combat_table is not None and self.combat_slot is not None:
            self._combat = self.combat_table.combat_of(self.combat_slot)
            self.combat_table.release(self.combat_slot)
            self.combat_slot = None
        if self.presentation is not None:
            self.presentation.kill()
        if self.sprite_groups is not None and self in self.sprite_groups.fighters:
            self.sprite_groups.fighters.remove(self)
        self.vitals.unbind()

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

        if actual_damage > 0:
            self.render_hints.flash_timer = HitFlash.DURATION

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
        """Float or slam an airborne victim for ``duration``."""
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
                self.otg_timer = self.otg_guard_duration

    def _bounce_off_the_ground(self, fall_speed: float) -> None:
        """Rebound a launched fighter that hit the floor hard, once.

        The vertical counterpart of the wall bounce, and only for a fighter
        flying in its knockback state: a jump, a hop or a light pop lands as
        it always did. Decided here, on the landing edge, rather than in the
        collision pass, because a landing reaches the floor three ways there
        (a resolved overlap, a shallow one, the ground snap) and only this
        edge sees all of them. The floor flag stays set for this tick; the
        reaction states read ``velocity.y`` with it, so the rising fighter is
        not rubbed against the ground it is leaving.
        """
        if (
            CombatSettings.GROUND_BOUNCE_FACTOR <= 0.0
            or fall_speed < CombatSettings.GROUND_BOUNCE_MIN_SPEED
            or self.state_machine.current_state_name != state_names.KNOCKBACK
        ):
            return
        self.velocity.y = -fall_speed * CombatSettings.GROUND_BOUNCE_FACTOR
        self.velocity.x *= CombatSettings.GROUND_BOUNCE_KEEP

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
        """Delegate to :class:`AnimationPublisher`; subclasses keep the art key."""
        self._animation_publisher.update(delta_time)

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
        self.render_hints.tick(delta_time)

        self._pre_update(delta_time)
        self._update_state_machine(delta_time)
        self.combat.update(delta_time)
        was_grounded = bool(self.on_surface.get("floor", False))
        fall_speed = float(self.velocity.y)
        self.move(delta_time, apply_gravity=True)
        now_grounded = bool(self.on_surface.get("floor", False))
        # Landing edge with the pre-move fall speed: hard landings become
        # dust puffs in PhysicsSystem; anything else zeroes the hint.
        landed = now_grounded and not was_grounded
        self.render_hints.landed_impact = fall_speed if landed else 0.0
        if landed:
            self._bounce_off_the_ground(fall_speed)
        self._tick_juggle(delta_time, was_grounded)
        self._tick_stun(delta_time)
        self.combat.sync_attack_box()
        self._post_update(delta_time)
        self._update_animator(delta_time)

    def save_state(self) -> EntitySnapshot:
        """Capture the full simulation state for rollback.

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
        snap.groups = list(self.presentation.groups()) if self.presentation is not None else []
        snap.extra = {
            "gravity_scale": self.gravity_scale,
            "juggle_timer": self.juggle_timer,
            "otg_timer": self.otg_timer,
            "parries_given": self.parries_given,
            "stun": self.stun,
            "stun_max": self.stun_max,
            "stun_duration": self.stun_duration,
            "stun_decay_delay": self.stun_decay_delay,
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
        # P1 / P2: ``prev`` is re-derived at the next frontier capture;
        # no snapshot field carries it across a rollback.
        self._prev_hurtboxes = ()
        self._prev_pushbox = None
        self._previous_contact_shape = None
        self.velocity = Vector2(snapshot.velocity)
        self.on_surface = dict(snapshot.on_surface)
        self.facing_right = snapshot.facing_right
        self.move_axis = snapshot.move_axis
        self.pushable = snapshot.pushable
        self.rng.setstate(snapshot.rng_state)
        self.vitals.load_state(snapshot.vitals)
        self.combat.load_state(snapshot.combat)
        self.combat.verify_geometry_checksum(snapshot.combat.geometry_checksum)
        self.state_machine.load_state(snapshot.state_machine)
        extra = snapshot.extra or {}
        self.gravity_scale = float(extra.get("gravity_scale", 1.0))
        self.juggle_timer = float(extra.get("juggle_timer", 0.0))
        self.otg_timer = float(extra.get("otg_timer", 0.0))
        self.parries_given = int(extra.get("parries_given", 0))
        self.stun = float(extra.get("stun", 0.0))
        self.stun_max = float(extra["stun_max"]) if extra.get("stun_max") is not None else None
        self.stun_duration = float(extra.get("stun_duration", 0.0))
        self.stun_decay_delay = float(extra.get("stun_decay_delay", 0.0))
