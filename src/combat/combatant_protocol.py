"""Protocols defining the interfaces required by the combat system.

These runtime-checkable protocols describe the minimal surface an entity
must expose so that the combat system can apply damage, knockback, stagger,
and other effects. They decouple the combat logic from any concrete entity
class.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import pygame

from src.combat.damage_types import DamageType
from src.combat.frame_data import Height, PhaseDefinition, Stance
from src.combat.knockback import KnockbackConfig
from src.combat.shapes import ShapePose, SweptShape


@dataclass(frozen=True)
class DamageResult:
    """Explicit outcome of a call to ``receive_damage``."""

    applied: bool = False
    guarded: bool = False
    killed: bool = False
    actual_damage: float = 0.0
    heavy_knockback: bool = False
    stunned: bool = False
    """The hit filled the target's stun gauge."""
    executed: bool = False
    """The hit killed a helpless target outright."""
    doomed: bool = False
    """The hit brought the target to nothing: it waits for the death blow."""
    evaded: bool = False
    """The target dodged the hit at the last moment: a dark step."""


class Finish(Enum):
    """What a fighter's blow does to a target it would kill."""

    NONE = "none"
    """It kills it."""
    DOOM = "doom"
    """It leaves it doomed, waiting for a death blow."""
    KILL = "kill"
    """Every blow kills, whatever the target has left."""


class AttackStatePort(Protocol):
    """Attack-state surface consumed by combat orchestration."""

    @property
    def is_active(self) -> bool: ...

    @property
    def is_attacking(self) -> bool: ...

    @property
    def targets_hit(self) -> set[str]: ...

    def take_launches(self) -> list[tuple[str, float]]:
        """The shots thrown since the last call, with their charge."""
        ...


class AttackComboPort(Protocol):
    """Air-combo tracking consumed from an attacker's combat."""

    @property
    def air_combo_count(self) -> int: ...

    def record_hit_landed(self, airborne: bool) -> bool: ...


class AttackerPort(Protocol):
    """Hit carrier: hitbox plus combo tracking, nothing else."""

    hitbox: pygame.FRect

    @property
    def combat(self) -> AttackComboPort: ...

    @property
    def finish(self) -> Finish:
        """What this carrier's blow does to a target it would kill."""
        ...

    def on_hit_confirmed(
        self, target: Combatant, combo_advanced: bool, result: DamageResult
    ) -> None:
        """One of this carrier's hits took health off ``target``.

        ``combo_advanced`` is whether the hit moved the combo counter, which
        happens once per attack however many targets it reached; ``result``
        is what the hit did.
        """
        ...


class CombatPort(AttackComboPort, Protocol):
    """Minimal combat component surface exposed by a combatant.

    P1 sweep members: ``swept_attack_boxes`` feeds the grid query and the
    contact test; ``capture_attack_origin`` is the tick-frontier hook.
    """

    @property
    def is_hurt(self) -> bool: ...

    @property
    def hurt_timer(self) -> float: ...

    @hurt_timer.setter
    def hurt_timer(self, value: float) -> None: ...

    @property
    def state(self) -> AttackStatePort: ...

    @property
    def attack_box(self) -> pygame.FRect | None: ...

    @property
    def attack_boxes(self) -> tuple[pygame.FRect, ...]: ...

    @property
    def swept_attack_boxes(self) -> tuple[pygame.FRect, ...]: ...

    @property
    def attack_shapes(self) -> tuple[ShapePose, ...]: ...

    @property
    def swept_attack_shapes(self) -> tuple[SweptShape, ...]: ...

    @property
    def attack_anchors(self) -> tuple[tuple[float, float], ...]: ...

    @property
    def current_phase(self) -> PhaseDefinition | None: ...

    @property
    def charge_multiplier(self) -> float: ...

    @property
    def targets_hit(self) -> set[str]: ...

    @property
    def movement_multiplier(self) -> float: ...

    @property
    def air_combo_count(self) -> int: ...

    def record_hit_landed(self, airborne: bool) -> bool: ...

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None: ...

    def cancel_attack(self) -> None: ...

    def reset_hurt_state(self) -> None: ...

    def sync_attack_box(self) -> None: ...

    def capture_attack_origin(self) -> None: ...

    def can_contact(self, target_id: str) -> bool: ...

    def record_contact(self, target_id: str) -> None: ...

    def reset(self) -> None: ...


class Combatant(Protocol):
    """Protocol defining the minimal interface an entity must expose for combat.

    Attributes
    ----------
    id : str
        Unique identifier for the entity.
    velocity : pygame.math.Vector2
        Current movement velocity of the entity (px/s).
    hitbox : pygame.FRect
        Collision rectangle representing the entity's body.
    hurtbox : pygame.FRect
        Union of the damage-receiving zones that incoming attacks must
        overlap to register a hit.
    hurtboxes : tuple[pygame.FRect, ...]
        Every damage-receiving zone (P2; single legacy zone by default).
    faction : str | None
        Faction identifier for friendly-fire rules.
    facing_right : bool
        True if the entity is currently facing right.
    is_dead : bool
        True if the entity's health has reached zero.
    combat : CombatPort
        The entity's combat component through its explicit public port.
    state_machine : Any
        The entity's state machine for state-based logic (optional, for DIZZY checks).
    stance : Stance
        The posture the entity is in, read by the attack policy to decide which
        moves are available. Defaults to GROUND on `Entity`; the player resolves
        it from its contacts, wall first.
    """

    id: str
    velocity: pygame.math.Vector2
    hitbox: pygame.FRect
    faction: str
    facing_right: bool
    on_surface: dict[str, bool]
    otg_timer: float
    state_machine: Any

    @property
    def is_dead(self) -> bool:
        """True if the entity's health has reached zero."""
        ...

    @property
    def stance(self) -> Stance:
        """The posture this entity is in."""
        ...

    @property
    def combat(self) -> CombatPort:
        """Combat operations exposed to gameplay systems."""
        ...

    @property
    def hurtbox(self) -> pygame.FRect:
        """Collision rectangle used for incoming attacks (union of zones)."""
        ...

    @property
    def hurtboxes(self) -> tuple[pygame.FRect, ...]:
        """Every damage-receiving zone (P2; single legacy zone by default)."""
        ...

    @property
    def hurtbox_mult(self) -> tuple[float, ...]:
        """Per-zone localized damage multipliers (parallel to ``hurtboxes``)."""
        ...

    @property
    def hurtbox_tags(self) -> tuple[tuple[str, ...], ...]:
        """Per-zone reserved invulnerability tags (parallel to ``hurtboxes``)."""
        ...

    @property
    def hurtbox_zone_names(self) -> tuple[str, ...]:
        """Per-zone debug names (parallel to ``hurtboxes``)."""
        ...

    def swept_hurtboxes(self) -> tuple[pygame.FRect, ...]:
        """Per-zone swept rectangles for the current tick (P1 sweep)."""
        ...

    def swept_hurtbox(self) -> pygame.FRect:
        """Union of the per-zone swept rectangles (legacy single-view API)."""
        ...

    @property
    def is_stunned(self) -> bool:
        """Whether the entity is stunned: helpless, and open to a throw."""
        ...

    @property
    def is_doomed(self) -> bool:
        """Whether the entity was brought to nothing and waits for the death blow."""
        ...

    @property
    def is_helpless(self) -> bool:
        """Stunned, on the ground or doomed: an ``execute`` hit kills it outright."""
        ...

    doomable: bool
    """Whether a blow that would kill it leaves it doomed instead (see :class:`Finish`)."""

    def doom(self) -> None:
        """Leave the entity doomed: all but dead, waiting for the death blow."""
        ...

    def recover_from_doom(self) -> None:
        """A death blow missed: the doomed entity gets back up with some health."""
        ...

    def guards_against(self, height: Height, unblockable: bool, source_center_x: float) -> bool:
        """Whether the entity's guard stops a hit at ``height`` coming from that side.

        An ``unblockable`` hit is never stopped, and breaks the guard it meets.
        """
        ...

    def add_stun(self, amount: float) -> bool:
        """Fill the stun gauge by ``amount``; True if that stunned the entity."""
        ...

    dodge_ghost: pygame.FRect | None
    """Where the entity stood when it began a dodge that can still be a perfect
    one, or ``None``. A hit that reaches this box was dodged at the last moment."""

    def on_hit_evaded(self) -> bool:
        """A hit passed through this entity while it was invincible, or through its ghost.

        True if that was a perfect dodge, which is reported once per dodge.
        """
        ...

    @property
    def is_invincible(self) -> bool:
        """Whether the current state ignores every hit (dash, launch...)."""
        ...

    contact_shape: ShapePose
    """The body's own contact shape, for momentum contact."""

    def swept_contact_shapes(self) -> tuple[SweptShape, ...]:
        """The contact shape swept since the last capture."""
        ...

    def swept_pushbox(self) -> pygame.FRect:
        """Physical body rectangle swept over the current tick."""
        ...

    def capture_sweep_origin(self) -> None:
        """Freeze the current zones as the next tick's sweep origin."""
        ...

    @property
    def health(self) -> float:
        """Current hit points of the entity."""
        ...

    @health.setter
    def health(self, value: float) -> None: ...

    @property
    def max_health(self) -> float:
        """Maximum hit points of the entity."""
        ...

    def receive_damage(
        self,
        amount: float,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
        interrupt: bool = True,
    ) -> DamageResult:
        """Apply raw damage and knockback to the entity.

        Guards are not asked here: a hazard or a body contact lands on a
        guarding fighter. An attack is checked against the guard first, by
        ``HitResolver`` through :meth:`guards_against`.

        Returns
        -------
        DamageResult
            Explicit damage and reaction outcome.
        """
        ...

    def stagger(self, duration: float) -> None:
        """Stun the entity, preventing it from acting for ``duration`` seconds.

        Parameters
        ----------
        duration : float
            Stun duration in seconds.
        """
        ...

    def set_juggle(self, gravity_mult: float, duration: float) -> None:
        """Apply an airborne gravity multiplier for ``duration``."""
        ...

    def die(self) -> None:
        """Handle the entity's death."""
        ...

    def get_damage_modifier(self, damage_type: DamageType) -> float:
        """Return the damage multiplier for a given damage type.

        Parameters
        ----------
        damage_type : DamageType
            The category of incoming damage.

        Returns
        -------
        float
            Multiplier applied to the raw damage amount.
        """
        ...

    @property
    def has_super_armor(self) -> bool:
        """Whether the entity currently has super armor."""
        ...

    def break_super_armor(self) -> None:
        """Break the entity's super armor, allowing stagger again."""
        ...

    def on_clash(self, other: Combatant) -> None:
        """This fighter's attack and ``other``'s cancelled each other."""
        ...

    @property
    def counter_covered(self) -> bool:
        """Whether this fighter is striking back behind its guard: a blade it meets bounces off."""
        ...

    def on_deflected(self, source_center_x: float) -> None:
        """This fighter's blow was stopped by a guard on the side of ``source_center_x``."""
        ...
