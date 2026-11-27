"""Dense ownership of the behaviour-rich combat component.

``CombatComponent`` keeps its state machine and rules; what moves into the
table is the ownership of the component object itself, so systems can resolve
a fighter's combat by dense slot instead of by attribute walk on a sprite.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

from src.simulation.ecs.table import DenseTable, Handle

if TYPE_CHECKING:
    from src.simulation.combat.combat_component import CombatComponent, NullCombatComponent
    from src.simulation.entities.entity import Entity


class CombatTable(DenseTable):
    """One combat component per fighter, keyed by object identity."""

    def __init__(self) -> None:
        super().__init__(("combat", "owner"))

    def register(self, entity: Entity) -> int:
        handle: Handle = (f"c{id(entity)}", 0)
        slot = self.acquire(handle)
        self.column("owner")[slot] = entity
        self.column("combat")[slot] = entity._combat
        return slot

    def combat_of(self, slot: int) -> CombatComponent | NullCombatComponent:
        return cast("CombatComponent | NullCombatComponent", self.column("combat")[slot])

    def iter_entities(self) -> Iterator[Entity]:
        """The fighters in row order, for systems that read combat state."""
        for slot in self.alive:
            yield self.column("owner")[slot]
