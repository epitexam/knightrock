"""Dense kinematic state with stable views over the columns.

``entity.velocity.x = ...`` and ``entity.on_surface["floor"] = ...`` are the
spelling used by the physics package in over a hundred places. The views below
keep that spelling while the values live in primitive columns: a view is
allocated once per entity, so mutation reaches the row without any call site
needing to know about the table.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from pygame.math import Vector2

from src.simulation.ecs.table import DenseTable, Handle

if TYPE_CHECKING:
    from src.simulation.entities.entity import Entity

_SURFACE_FLAGS = ("floor", "left", "right")


class Vector2View:
    """A stable ``Vector2``-like view over two float columns."""

    def __init__(self, table: MovementTable, slot: int, mirror: Any) -> None:
        self._table = table
        self._slot = slot
        self._mirror = mirror
        # DenseTable never replaces a column list: it mutates it in place.
        # Keeping the lists avoids one dict lookup on every read and write.
        self._vx = table.column("vx")
        self._vy = table.column("vy")

    @property
    def x(self) -> float:
        return float(self._vx[self._slot])

    @x.setter
    def x(self, value: float) -> None:
        self._vx[self._slot] = float(value)

    @property
    def y(self) -> float:
        return float(self._vy[self._slot])

    @y.setter
    def y(self, value: float) -> None:
        self._vy[self._slot] = float(value)

    def update(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def length(self) -> float:
        return Vector2(self.x, self.y).length()

    def copy(self) -> Vector2:
        return Vector2(self.x, self.y)

    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y

    def __len__(self) -> int:
        return 2

    def __getitem__(self, index: int) -> float:
        if index == 0:
            return self.x
        if index == 1:
            return self.y
        raise IndexError(index)

    def __repr__(self) -> str:
        return f"<Vector2View({self.x}, {self.y})>"


class SurfaceFlagsView:
    """A stable mapping view over the three boolean contact columns."""

    def __init__(self, table: MovementTable, slot: int, mirror: Any) -> None:
        self._table = table
        self._slot = slot
        self._mirror = mirror
        self._columns = {flag: table.column(flag) for flag in _SURFACE_FLAGS}

    def __getitem__(self, key: str) -> bool:
        if key not in self._columns:
            raise KeyError(key)
        return bool(self._columns[key][self._slot])

    def __setitem__(self, key: str, value: bool) -> None:
        if key not in self._columns:
            raise KeyError(key)
        self._columns[key][self._slot] = bool(value)

    def get(self, key: str, default: Any = None) -> Any:
        if key not in _SURFACE_FLAGS:
            return default
        return self[key]

    def keys(self) -> tuple[str, ...]:
        return _SURFACE_FLAGS

    def __iter__(self) -> Iterator[str]:
        return iter(_SURFACE_FLAGS)

    def __len__(self) -> int:
        return len(_SURFACE_FLAGS)

    def __repr__(self) -> str:
        return f"<SurfaceFlagsView({dict(self)})>"


class MovementTable(DenseTable):
    """Kinematic columns, registered from ``SpriteGroups.add_fighter``."""

    def __init__(self) -> None:
        super().__init__(("vx", "vy", "floor", "left", "right", "owner"))
        self._views: dict[int, tuple[Vector2View, SurfaceFlagsView]] = {}

    def register(self, entity: Entity) -> int:
        """Give one fighter a row and two stable views onto it."""
        # Ids from different factories can collide (a debug enemy may be e0
        # just like the level's player), so the row key is object identity.
        # A restored entity is the same object and gets the same key.
        handle: Handle = (f"m{id(entity)}", 0)
        slot = self.acquire(handle)
        self.column("owner")[slot] = entity
        self.column("vx")[slot] = float(entity._movement.velocity.x)
        self.column("vy")[slot] = float(entity._movement.velocity.y)
        for flag in _SURFACE_FLAGS:
            self.column(flag)[slot] = bool(entity._movement.on_surface.get(flag, False))
        movement = entity._movement
        self._views[slot] = (
            Vector2View(self, slot, movement),
            SurfaceFlagsView(self, slot, movement),
        )
        return slot

    def release(self, slot: int) -> Handle:
        self._views.pop(slot, None)
        return super().release(slot)

    def views_for(self, slot: int) -> tuple[Vector2View, SurfaceFlagsView]:
        return self._views[slot]

    def iter_entities(self) -> Iterator[Entity]:
        """The fighters in registration order, read from the dense rows."""
        for slot in self.alive:
            yield self.column("owner")[slot]
