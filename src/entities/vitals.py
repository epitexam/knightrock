"""Vitals: health, death flag, and status timers shared by all entities.

Extracted from ``Entity`` (ARCH-02, first step) so health and status
mechanics can be tested and evolved independently of the entity
aggregation layer.  ``Entity`` composes a :class:`Vitals` instance and
delegates its health/status attributes to it.
"""

from collections.abc import Callable

from pygame.math import Vector2


class Vitals:
    """Own an entity's health, death flag, and status timers.

    Parameters
    ----------
    health : float
        Starting health (clamped to ``[0, max_health]``).
    max_health : float
        Maximum health cap (never below 1.0).
    invincibility_duration : float
        I-frames granted after taking damage.
    spawn_pos : Vector2 | None
        Position used to reset the entity after death.
    on_death : Callable[[], None] | None
        Optional hook invoked the moment health reaches zero, so the
        owner can run entity-level cleanup (e.g. reset its combat state)
        without ``Vitals`` knowing about combat.
    """

    def __init__(
        self,
        health: float = 100.0,
        max_health: float = 100.0,
        invincibility_duration: float = 0.0,
        spawn_pos: Vector2 | None = None,
        on_death: Callable[[], None] | None = None,
    ) -> None:
        self._health: float = health
        self._max_health: float = max_health
        self._on_death = on_death

        self.is_dead: bool = False
        self.invincibility_timer: float = 0.0
        self.invincibility_duration: float = invincibility_duration
        self.stagger_timer: float = 0.0
        self.super_armor: bool = False
        self.super_armor_count: int = 0
        self.spawn_pos: Vector2 = spawn_pos if spawn_pos is not None else Vector2(0, 0)

    @property
    def health(self) -> float:
        """Current health, clamped to ``[0, max_health]``."""
        return self._health

    @health.setter
    def health(self, value: float) -> None:
        old = self._health
        self._health = max(0.0, min(value, self._max_health))
        if old > 0 and self._health == 0 and not self.is_dead:
            self.is_dead = True
            if self._on_death is not None:
                self._on_death()

    @property
    def max_health(self) -> float:
        """Maximum health cap (never below 1.0)."""
        return self._max_health

    @max_health.setter
    def max_health(self, value: float) -> None:
        self._max_health = max(1.0, value)

    def can_receive_damage(self) -> bool:
        """Whether the owner can currently take damage."""
        return not self.is_dead and self.invincibility_timer <= 0

    def apply_damage(self, amount: float) -> float:
        """Subtract health and return the actual damage dealt."""
        old_health = self._health
        self.health -= amount
        return old_health - self.health

    def set_invincibility(self) -> None:
        """Grant i-frames when an invincibility duration is configured."""
        if self.invincibility_duration > 0:
            self.invincibility_timer = self.invincibility_duration

    def tick_timers(self, delta_time: float) -> None:
        """Decay stagger and invincibility timers (never below zero)."""
        if self.stagger_timer > 0:
            self.stagger_timer = max(0.0, self.stagger_timer - delta_time)
        if self.invincibility_timer > 0:
            self.invincibility_timer = max(0.0, self.invincibility_timer - delta_time)

    def reset(self) -> None:
        """Restore health and clear all status timers and armor."""
        self.is_dead = False
        self.stagger_timer = 0.0
        self.super_armor = False
        self.super_armor_count = 0
        self.invincibility_timer = 0.0
        self.health = self._max_health
