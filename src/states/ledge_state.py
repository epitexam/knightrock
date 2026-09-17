"""Shared void-edge state for every entity with a state machine.

``LedgeState`` is the common answer to ``Entity.is_at_ledge``: stop dead,
turn from the void, hold a short beat, then hand control back through
``exit_resolver``. Only the enemy AI enters it (the player keeps control);
the parameterization (``exit_resolver``, hold, friction, tags) follows the
shared reaction states in :mod:`src.states.reaction_states`.
"""

from collections.abc import Callable
from typing import Any

from src.core.settings import Ledge
from src.physics import lerp_velocity
from src.states.state_machine import State

__all__ = ["LedgeState"]


class LedgeState(State):
    """At the void's edge: brake, turn around, wait out the hold beat."""

    def __init__(
        self,
        entity: Any,
        exit_resolver: Callable[[], str | None],
        *,
        hold_duration: float = Ledge.HOLD_DURATION,
        friction: float = Ledge.STOP_FRICTION,
        tags: list[str] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["ledge"])
        self.exit_resolver = exit_resolver
        self.hold_duration = hold_duration
        self.friction = friction
        self.hold_timer = 0.0

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Cut locomotion and turn from the void (no re-entry side effects)."""
        self.hold_timer = self.hold_duration
        self.entity.move_axis = 0.0
        self.entity.turn_around()

    def update(self, delta_time: float) -> str | None:
        """Brake while grounded, then leave once the edge is behind us.

        Turning flips the directional probe, so a turned entity normally
        clears on the first beat: lingering here means it is still facing
        the void (shoved back, turning into a wall) and it keeps waiting
        instead of walking off.
        """
        if self.entity.on_surface.get("floor", False):
            lerp_velocity(self.entity, 0.0, self.friction, delta_time)
        self.hold_timer -= delta_time
        if self.hold_timer <= 0.0 and not self.entity.is_at_ledge():
            return self.exit_resolver()
        return None
