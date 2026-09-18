"""MovementComponent: kinematic state and movement behaviour for an entity.

Extracted from ``Entity`` (audit Phase 3 #2) so the physics integration —
gravity, horizontal control, collision resolution, moving-platform carry —
lives in a dedicated component wired in like ``vitals``/``combat`` instead
of bloating the entity aggregate (audit F2.2).

The component follows the same owner-passed pattern as
``combat.hitbox`` (:class:`~src.combat.hitbox_manager.HitboxManager`): the
heavy lifting stays in the pure ``src.physics`` functions, which receive the
owning entity and read its geometry/parameters.  The component owns the
mutable kinematic state (``velocity``, ``on_surface``) so there is a single
source of truth, and exposes the movement verbs that drive the physics pass.

The per-entity *tuning* parameters (``speed``, ``floor_control``,
``air_control``, the gravity/drag coefficients, ``move_axis``) intentionally
stay on the entity: they are reassigned wholesale by subclasses such as
``Player``/``Enemy`` from their configs, and the physics functions read them
straight off the entity.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal

from pygame.math import Vector2

from src.physics import (
    apply_entity_gravity,
    apply_horizontal_movement,
    apply_moving_platform,
    move_entity,
    resolve_collisions,
    update_contact_state,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from src.entities.entity import Entity

__all__ = ["MovementComponent"]


class MovementComponent:
    """Own an entity's kinematic state and drive its per-tick movement.

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

    def apply_gravity(self, delta_time: float) -> None:
        """Apply gravity with drag, respecting wall sliding."""
        apply_entity_gravity(self._owner, delta_time)

    def apply_horizontal_movement(self, delta_time: float) -> None:
        """Apply horizontal acceleration and control based on ``move_axis``."""
        apply_horizontal_movement(self._owner, delta_time)

    def check_contact(self) -> None:
        """Update the floor/left/right surface contact flags."""
        update_contact_state(self._owner, self._owner.collision_sprites)

    def handle_collisions(self, axis: Literal["horizontal", "vertical"]) -> None:
        """Resolve collisions along a given axis."""
        resolve_collisions(self._owner, axis)

    def move(self, delta_time: float, apply_gravity: bool = True) -> None:
        """Move the entity based on velocity, resolving collisions."""
        move_entity(self._owner, delta_time, apply_gravity=apply_gravity)

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        """Carry the entity along moving platforms."""
        apply_moving_platform(self._owner, moving_platforms)

    def stop(self) -> None:
        """Zero the velocity (used by ``reset_position``)."""
        self.velocity = Vector2(0, 0)
