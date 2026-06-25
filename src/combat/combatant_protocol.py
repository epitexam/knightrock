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


@runtime_checkable
class BlockingCombatant(Combatant, Protocol):
    """Extends Combatant with blocking capabilities (used by Player)."""
    block_stamina: float

    @property
    def is_blocking(self) -> bool: ...