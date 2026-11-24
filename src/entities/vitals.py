"""Vitals: health, death flag, and status timers shared by all entities.

Extracted from ``Entity`` (ARCH-02, first step) so health and status
mechanics can be tested and evolved independently of the entity
aggregation layer.  ``Entity`` composes a :class:`Vitals` instance and
delegates its health/status attributes to it.

When the fighter lives in a level, the nine values live in a dense
:class:`~src.core.ecs.vitals_table.VitalsTable` row. The behaviour -- clamping,
the death hook, timer decay -- stays here: the table holds data, not rules.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pygame.math import Vector2

from src.core.ecs.vitals_table import VitalsTable


@dataclass(frozen=True)
class VitalsSnapshot:
    """Serializable capture of every vitals field (rollback, Phase 3 #3)."""

    health: float
    max_health: float
    is_dead: bool
    invincibility_timer: float
    invincibility_duration: float
    stagger_timer: float
    super_armor: bool
    super_armor_count: int
    spawn_pos: tuple[float, float]


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
        self._table: VitalsTable | None = None
        self._slot: int | None = None

        self.is_dead: bool = False
        self.invincibility_timer: float = 0.0
        self.invincibility_duration: float = invincibility_duration
        self.stagger_timer: float = 0.0
        self.super_armor: bool = False
        self.super_armor_count: int = 0
        self.spawn_pos: Vector2 = spawn_pos if spawn_pos is not None else Vector2(0, 0)

    def bind(self, table: VitalsTable) -> None:
        """Attach this component to a level's vitals table, once."""
        if self._table is table:
            return
        if self._table is not None and self._slot is not None:
            self._table.release(self._slot)
        self._table = table
        self._slot = table.register(self)

    def unbind(self) -> None:
        """Detach before the owner is killed and its row is reclaimed."""
        if self._table is not None and self._slot is not None:
            for name in ("health", "max_health", "is_dead", "invincibility_timer",
                         "invincibility_duration", "stagger_timer", "super_armor",
                         "super_armor_count"):
                self.__dict__[f"_{name}" if name in ("health", "max_health") else name] = (
                    self._table.column(name)[self._slot]
                )
            self._table.release(self._slot)
        self._table = None
        self._slot = None

    def _get(self, name: str) -> Any:
        if self._table is not None and self._slot is not None:
            return self._table.column(name)[self._slot]
        key = f"_{name}" if name in ("health", "max_health") else name
        return self.__dict__.get(key)

    def _set(self, name: str, value: Any) -> None:
        if self._table is not None and self._slot is not None:
            self._table.column(name)[self._slot] = value
            return
        key = f"_{name}" if name in ("health", "max_health") else name
        self.__dict__[key] = value

    @property
    def health(self) -> float:
        """Current health, clamped to ``[0, max_health]``."""
        return float(self._get("health"))

    @health.setter
    def health(self, value: float) -> None:
        old = float(self._get("health"))
        capped = max(0.0, min(value, float(self._get("max_health"))))
        self._set("health", capped)
        if old > 0 and capped == 0 and not bool(self._get("is_dead")):
            self._set("is_dead", True)
            if self._on_death is not None:
                self._on_death()

    @property
    def max_health(self) -> float:
        """Maximum health cap (never below 1.0)."""
        return float(self._get("max_health"))

    @max_health.setter
    def max_health(self, value: float) -> None:
        self._set("max_health", max(1.0, value))

    @property
    def is_dead(self) -> bool:
        return bool(self._get("is_dead"))

    @is_dead.setter
    def is_dead(self, value: bool) -> None:
        self._set("is_dead", bool(value))

    @property
    def invincibility_timer(self) -> float:
        return float(self._get("invincibility_timer"))

    @invincibility_timer.setter
    def invincibility_timer(self, value: float) -> None:
        self._set("invincibility_timer", float(value))

    @property
    def invincibility_duration(self) -> float:
        return float(self._get("invincibility_duration"))

    @invincibility_duration.setter
    def invincibility_duration(self, value: float) -> None:
        self._set("invincibility_duration", float(value))

    @property
    def stagger_timer(self) -> float:
        return float(self._get("stagger_timer"))

    @stagger_timer.setter
    def stagger_timer(self, value: float) -> None:
        self._set("stagger_timer", float(value))

    @property
    def super_armor(self) -> bool:
        return bool(self._get("super_armor"))

    @super_armor.setter
    def super_armor(self, value: bool) -> None:
        self._set("super_armor", bool(value))

    @property
    def super_armor_count(self) -> int:
        return int(self._get("super_armor_count"))

    @super_armor_count.setter
    def super_armor_count(self, value: int) -> None:
        self._set("super_armor_count", int(value))

    def can_receive_damage(self) -> bool:
        """Whether the owner can currently take damage."""
        return not bool(self._get("is_dead")) and float(self._get("invincibility_timer")) <= 0

    def apply_damage(self, amount: float) -> float:
        """Subtract health and return the actual damage dealt."""
        old_health = float(self._get("health"))
        self.health -= amount
        return old_health - float(self._get("health"))

    def set_invincibility(self) -> None:
        """Grant i-frames when an invincibility duration is configured."""
        duration = float(self._get("invincibility_duration"))
        if duration > 0:
            self._set("invincibility_timer", duration)

    def tick_timers(self, delta_time: float) -> None:
        """Decay stagger and invincibility timers (never below zero)."""
        stagger = float(self._get("stagger_timer"))
        if stagger > 0:
            self._set("stagger_timer", max(0.0, stagger - delta_time))
        invincible = float(self._get("invincibility_timer"))
        if invincible > 0:
            self._set("invincibility_timer", max(0.0, invincible - delta_time))

    def reset(self) -> None:
        """Restore health and clear all status timers and armor."""
        self._set("is_dead", False)
        self._set("stagger_timer", 0.0)
        self._set("super_armor", False)
        self._set("super_armor_count", 0)
        self._set("invincibility_timer", 0.0)
        self.health = float(self._get("max_health"))

    def save_state(self) -> VitalsSnapshot:
        """Capture every field for rollback."""
        return VitalsSnapshot(
            health=float(self._get("health")),
            max_health=float(self._get("max_health")),
            is_dead=bool(self._get("is_dead")),
            invincibility_timer=float(self._get("invincibility_timer")),
            invincibility_duration=float(self._get("invincibility_duration")),
            stagger_timer=float(self._get("stagger_timer")),
            super_armor=bool(self._get("super_armor")),
            super_armor_count=int(self._get("super_armor_count")),
            spawn_pos=(self.spawn_pos.x, self.spawn_pos.y),
        )

    def load_state(self, snapshot: VitalsSnapshot) -> None:
        """Restore every field from a rollback snapshot.

        ``health`` is written directly (not through the ``health``
        property) so a restore never re-triggers the death hook: the
        snapshot already carries the authoritative ``is_dead`` flag.
        """
        self._set("health", snapshot.health)
        self._set("max_health", snapshot.max_health)
        self._set("is_dead", snapshot.is_dead)
        self._set("invincibility_timer", snapshot.invincibility_timer)
        self._set("invincibility_duration", snapshot.invincibility_duration)
        self._set("stagger_timer", snapshot.stagger_timer)
        self._set("super_armor", snapshot.super_armor)
        self._set("super_armor_count", snapshot.super_armor_count)
        self.spawn_pos = Vector2(snapshot.spawn_pos)
        if self._table is not None and self._slot is not None:
            self._table.column("spawn_x")[self._slot] = self.spawn_pos.x
            self._table.column("spawn_y")[self._slot] = self.spawn_pos.y
