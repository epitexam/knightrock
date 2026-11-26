"""Dense geometry rows: one owned pushbox per fighter.

The pushbox is the collider every physics and combat system reads. The table
owns the ``FRect`` object so a system can iterate the column without walking
sprite groups; the object itself is kept whole because its mutation API
(``center``, ``midbottom``, ``inflate_ip``, ``colliderect``) is used in over a
hundred places and re-implementing it as a view would be a different, riskier
change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.simulation.ecs.table import DenseTable, Handle

if TYPE_CHECKING:
    from src.simulation.entities.entity import Entity


class GeometryTable(DenseTable):
    """The fighters' pushboxes, keyed by object identity."""

    def __init__(self) -> None:
        super().__init__(("hitbox", "owner"))

    def register(self, entity: Entity) -> int:
        handle: Handle = (f"g{id(entity)}", 0)
        slot = self.acquire(handle)
        self.column("owner")[slot] = entity
        self.column("hitbox")[slot] = entity._pushbox
        return slot

    def hitbox_of(self, slot: int) -> pygame.FRect:
        box: pygame.FRect = self.column("hitbox")[slot]
        return box
