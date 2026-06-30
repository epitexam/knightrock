"""
Protocols defining the interfaces required by the combat system.
"""
from typing import Protocol, runtime_checkable, Any, TYPE_CHECKING
import pygame

from src.combat.attack_types import KnockbackConfig
from src.combat.damage_types import DamageType

if TYPE_CHECKING:
    from src.combat.combat import CombatComponent


@runtime_checkable
class Combatant(Protocol):
    """Protocol defining the minimal interface required by the combat system."""
    velocity: pygame.math.Vector2
    hitbox: pygame.FRect
    hurtbox: pygame.FRect
    faction: str | None
    facing_right: bool
    combat: Any

    @property
    def health(self) -> float: ...

    @health.setter
    def health(self, value: float) -> None: ...

    @property
    def max_health(self) -> float: ...

    def receive_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None: ...

    def stagger(self, duration: float) -> None: ...

    def die(self) -> None: ...

    def get_damage_modifier(self, damage_type: DamageType) -> float:
        """Returns the damage multiplier for a given type"""
        ...

    @property
    def has_super_armor(self) -> bool:
        """Returns whether the entity currently has super armor."""
        ...

    def break_super_armor(self) -> None:
        """Breaks the entity's super armor."""
        ...


@runtime_checkable
class BlockingCombatant(Combatant, Protocol):
    """Extends Combatant with blocking capabilities."""
    block_stamina: float

    @property
    def is_blocking(self) -> bool: ...
