"""Dense vitals columns with the behaviour still owned by ``Vitals``.

The health setter owns the death hook and the clamp; the table only holds the
values. Standalone fighters keep the plain component, so tests that build a
``Vitals`` on its own are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.ecs.table import DenseTable, Handle

if TYPE_CHECKING:
    from src.entities.vitals import Vitals

_COLUMNS = (
    "health",
    "max_health",
    "is_dead",
    "invincibility_timer",
    "invincibility_duration",
    "stagger_timer",
    "super_armor",
    "super_armor_count",
    "spawn_x",
    "spawn_y",
    "owner",
)


class VitalsTable(DenseTable):
    """Vitals rows, keyed by the owning object's identity."""

    def __init__(self) -> None:
        super().__init__(_COLUMNS)

    def register(self, vitals: Vitals) -> int:
        handle: Handle = (f"v{id(vitals)}", 0)
        slot = self.acquire(handle)
        self.write(slot, vitals)
        return slot

    def write(self, slot: int, vitals: Vitals) -> None:
        self.column("health")[slot] = vitals._health
        self.column("max_health")[slot] = vitals._max_health
        self.column("is_dead")[slot] = vitals.is_dead
        self.column("invincibility_timer")[slot] = vitals.invincibility_timer
        self.column("invincibility_duration")[slot] = vitals.invincibility_duration
        self.column("stagger_timer")[slot] = vitals.stagger_timer
        self.column("super_armor")[slot] = vitals.super_armor
        self.column("super_armor_count")[slot] = vitals.super_armor_count
        self.column("spawn_x")[slot] = vitals.spawn_pos.x
        self.column("spawn_y")[slot] = vitals.spawn_pos.y
        self.column("owner")[slot] = vitals

    def assert_mirror(self, slot: int) -> None:
        vitals: Any = self.column("owner")[slot]
        assert self.column("health")[slot] == vitals._health
        assert self.column("max_health")[slot] == vitals._max_health
        assert self.column("is_dead")[slot] == vitals.is_dead
        assert self.column("invincibility_timer")[slot] == vitals.invincibility_timer
        assert self.column("stagger_timer")[slot] == vitals.stagger_timer
        assert self.column("spawn_x")[slot] == vitals.spawn_pos.x
        assert self.column("spawn_y")[slot] == vitals.spawn_pos.y
