"""Protocols defining the interfaces required by the combat system.

These runtime-checkable protocols describe the minimal surface an entity
must expose so that the combat system can apply damage, knockback, stagger,
and other effects. They decouple the combat logic from any concrete entity
class.
"""

from typing import Any, Protocol, runtime_checkable

import pygame

from src.combat.damage_types import DamageType
from src.combat.knockback import KnockbackConfig


@runtime_checkable
class Combatant(Protocol):
    """Protocol defining the minimal interface an entity must expose for combat.

    Attributes
    ----------
    id : int
        Unique network identifier for the entity.
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
    combat : Any
        The entity's CombatComponent-like object.
    """

    id: int
    velocity: pygame.math.Vector2
    hitbox: pygame.FRect
    hurtbox: pygame.FRect
    faction: str | None
    facing_right: bool
    is_dead: bool
    combat: Any

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
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None:
        """Apply raw damage and knockback to the entity.

        Parameters
        ----------
        amount : int
            Hit points to subtract.
        source_center_x : float | None
            X centre of the damage source.
        knockback : KnockbackConfig | None
            Knockback impulse.
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
