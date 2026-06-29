from typing import Protocol, runtime_checkable
import pygame
from src.combat.attack_types import KnockbackConfig


@runtime_checkable
class Combatant(Protocol):
    """Protocol defining the minimal interface required by CombatComponent."""
    velocity: pygame.math.Vector2
    hitbox: pygame.FRect
    facing_right: bool

    @property
    def health(self) -> float:
        """Return current health."""
        ...

    @health.setter
    def health(self, value: float) -> None:
        """Set current health."""
        ...

    @property
    def max_health(self) -> float:
        """Return maximum health."""
        ...

    def receive_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None:
        """Apply damage from a source and optional knockback."""
        ...


@runtime_checkable
class BlockingCombatant(Combatant, Protocol):
    """Extends Combatant with blocking capabilities (used by Player)."""
    block_stamina: float

    @property
    def is_blocking(self) -> bool:
        """Return whether the combatant is currently blocking."""
        ...