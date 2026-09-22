"""Protocols defining the interfaces required by the combat system.

These runtime-checkable protocols describe the minimal surface an entity
must expose so that the combat system can apply damage, knockback, stagger,
and other effects. They decouple the combat logic from any concrete entity
class.
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import pygame

from src.combat.damage_types import DamageType
from src.combat.frame_data import PhaseDefinition
from src.combat.knockback import KnockbackConfig


@dataclass(frozen=True)
class DamageResult:
    """Explicit outcome of a call to ``receive_damage``."""

    applied: bool = False
    guarded: bool = False
    parried: bool = False
    guard_broken: bool = False
    killed: bool = False
    actual_damage: float = 0.0
    heavy_knockback: bool = False


class AttackStatePort(Protocol):
    """Attack-state surface consumed by combat orchestration."""

    @property
    def is_active(self) -> bool: ...

    @property
    def is_attacking(self) -> bool: ...

    @property
    def targets_hit(self) -> set[str]: ...


@runtime_checkable
class AttackComboPort(Protocol):
    """Air-combo tracking consumed from an attacker's combat."""

    @property
    def air_combo_count(self) -> int: ...

    def record_hit_landed(self, airborne: bool) -> None: ...


@runtime_checkable
class AttackerPort(Protocol):
    """Hit carrier: hitbox plus combo tracking, nothing else."""

    hitbox: pygame.FRect

    @property
    def combat(self) -> AttackComboPort: ...


@runtime_checkable
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
    def current_phase(self) -> PhaseDefinition | None: ...

    @property
    def charge_multiplier(self) -> float: ...

    @property
    def targets_hit(self) -> set[str]: ...

    @property
    def movement_multiplier(self) -> float: ...

    @property
    def air_combo_count(self) -> int: ...

    def record_hit_landed(self, airborne: bool) -> None: ...

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None: ...

    def cancel_attack(self) -> None: ...

    def reset_hurt_state(self) -> None: ...

    def sync_attack_box(self) -> None: ...

    def capture_attack_origin(self) -> None: ...

    def can_contact(self, target_id: str) -> bool: ...

    def record_contact(self, target_id: str) -> None: ...

    def reset(self) -> None: ...


@runtime_checkable
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

    def capture_sweep_origin(self) -> None:
        """Freeze the current zones as the next tick's sweep origin (P1/D3)."""
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
        unblockable: bool = False,
        height: str = "mid",
    ) -> DamageResult:
        """Apply raw damage and knockback to the entity.

        Parameters
        ----------
        amount : float
            Hit points to subtract.
        source_center_x : float | None
            X centre of the damage source.
        knockback : KnockbackConfig | None
            Knockback impulse.
        interrupt : bool
            Whether the hit may interrupt the current action.
        unblockable : bool
            Whether the hit bypasses guard and parry.
        height : str
            Guard height checked against the crouch state.

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


@runtime_checkable
class GuardingCombatant(Combatant, Protocol):
    """Extends ``Combatant`` with directional guard capabilities."""

    guard_posture: float

    @property
    def is_guarding(self) -> bool:
        """Whether the entity is currently in a guarding state."""
        ...
