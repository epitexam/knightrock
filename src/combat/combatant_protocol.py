"""Protocols defining the interfaces required by the combat system.

These runtime-checkable protocols describe the minimal surface an entity
must expose so that the combat system can apply damage, knockback, stagger,
and other effects. They decouple the combat logic from any concrete entity
class.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pygame

from src.combat.damage_types import DamageType
from src.combat.frame_data import PhaseDefinition
from src.combat.knockback import KnockbackConfig


@dataclass(frozen=True)
class DamageResult:
    """Explicit outcome of a call to ``receive_damage``."""

    applied: bool = False
    blocked: bool = False
    killed: bool = False
    actual_damage: float = 0.0
    heavy_knockback: bool = False


class AttackStatePort(Protocol):
    """Attack-state surface consumed by combat orchestration."""

    is_active: bool
    is_attacking: bool
    targets_hit: set[str]


class CombatPort(Protocol):
    """Minimal combat component surface exposed by a combatant."""

    is_hurt: bool
    hurt_timer: float

    @property
    def state(self) -> AttackStatePort: ...

    @property
    def attack_box(self) -> pygame.FRect | None: ...

    @property
    def current_phase(self) -> PhaseDefinition | None: ...

    @property
    def charge_multiplier(self) -> float: ...

    @property
    def targets_hit(self) -> set[str]: ...

    @property
    def movement_multiplier(self) -> float: ...

    def on_hit(
        self, duration: float | None = None, interrupt: bool = True
    ) -> None: ...

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
        Rectangle that incoming attacks must overlap to register a hit.
    faction : str | None
        Faction identifier for friendly-fire rules.
    facing_right : bool
        True if the entity is currently facing right.
    is_dead : bool
        True if the entity's health has reached zero.
    combat : CombatPort
        The entity's combat component through its explicit public port.
    """

    id: str
    velocity: pygame.math.Vector2
    hitbox: pygame.FRect
    faction: str
    facing_right: bool
    is_dead: bool
    @property
    def combat(self) -> CombatPort:
        """Combat operations exposed to gameplay systems."""
        ...

    @property
    def hurtbox(self) -> pygame.FRect:
        """Collision rectangle used for incoming attacks."""
        ...

    @property
    def health(self) -> float:
        """Current hit points of the entity."""
        ...

    @health.setter
    def health(self, value: float) -> None:
        ...

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
class BlockingCombatant(Combatant, Protocol):
    """Extends ``Combatant`` with blocking capabilities.

    Attributes
    ----------
    block_stamina : float
        Remaining stamina available for blocking.
    """

    block_stamina: float

    @property
    def is_blocking(self) -> bool:
        """Whether the entity is currently in a blocking state."""
        ...
