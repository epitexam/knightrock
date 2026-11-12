"""MovementComponent: the kinematic state of an entity.

It owns ``velocity`` and the ``on_surface`` contact flags, the state the
physics pass reads and writes every tick. The movement itself is the pure
functions of ``src.physics``, which ``Entity`` calls directly with itself: the
component used to relay each of them, which made one call three deep for
nothing.

The per-entity *tuning* (``speed``, ``floor_control``, the gravity and drag
coefficients, ``move_axis``) stays on the entity, where ``Player`` and ``Enemy``
set it from their configs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pygame.math import Vector2

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from src.entities.entity import Entity

__all__ = ["MovementComponent"]


class MovementComponent:
    """Own an entity's kinematic state.

    Parameters
    ----------
    owner : Entity
        The entity that owns this component. The pure physics functions are
        called with this entity so they can read its geometry (``hitbox``,
        ``rect``), tuning parameters, and contact hooks.
    velocity : Vector2 | None
        Initial velocity vector; defaults to a zero vector.
    on_surface : dict[str, bool] | None
        Initial floor/left/right contact flags; defaults to all-False.
    """

    def __init__(
        self,
        owner: Entity,
        velocity: Vector2 | None = None,
        on_surface: dict[str, bool] | None = None,
    ) -> None:
        self._owner = owner
        self.velocity: Vector2 = velocity if velocity is not None else Vector2(0, 0)
        self.on_surface: dict[str, bool] = (
            on_surface
            if on_surface is not None
            else {"floor": False, "left": False, "right": False}
        )
