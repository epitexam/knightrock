"""Shared reaction states (hurt / knockback / stagger) for players and enemies.

These three states were duplicated between ``player_states.py`` and
``enemy_states.py`` with only small differences (ARCH-05).  The shared
logic is now parameterized by:

- ``exit_resolver``: a zero-argument callable returning the next state name
  (or ``None`` to stay) once the reaction completes.  Players resolve to
  ``ground_return``-style names; enemies resolve to ``"idle"``.
- ``on_enter``: optional callback invoked with the transition ``kwargs``,
  used for entity-specific setup (clearing the dash request, light knockback).
- ``friction``: drag coefficient applied to horizontal velocity (0 = none).
- ``tags``: state-machine tags preserved from the original classes.
"""

from typing import Any, Callable, Optional

from src.core.settings import Physics
from src.physics import lerp_velocity
from src.states.state_machine import State

# Horizontal speed (px/s) below which knockback is considered resolved.
KNOCKBACK_STOP_SPEED = 20.0
# Vertical speed (px/s) below which the launch is considered landed.
KNOCKBACK_STOP_VERTICAL = 1.0


class HurtState(State):
    """Reaction to taking damage: wait for the hurt timer to clear."""

    def __init__(
        self,
        entity: Any,
        exit_resolver: Callable[[], str | None],
        *,
        friction: float = 0.0,
        tags: Optional[list[str]] = None,
        on_enter: Optional[Callable[..., None]] = None,
    ) -> None:
        super().__init__(entity, tags or ["hurt", "busy"])
        self.exit_resolver = exit_resolver
        self.friction = friction
        self.on_enter = on_enter

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Run the optional setup hook with the transition kwargs."""
        if self.on_enter is not None:
            self.on_enter(**kwargs)

    def update(self, delta_time: float) -> Optional[str]:
        """Apply friction and leave the state once the hurt timer clears.

        Friction is applied unconditionally (even airborne) to match the
        original player hurt behaviour.
        """
        if self.friction > 0:
            lerp_velocity(self.entity, 0.0, self.friction, delta_time)
        if not self.entity.combat.is_hurt:
            return self.exit_resolver()
        return None


class KnockbackState(State):
    """Strong launch: wait for the entity to land and slow down."""

    def __init__(
        self,
        entity: Any,
        exit_resolver: Callable[[], str | None],
        *,
        friction: float = Physics.KNOCKBACK_FRICTION,
        tags: Optional[list[str]] = None,
        on_enter: Optional[Callable[..., None]] = None,
    ) -> None:
        super().__init__(entity, tags or ["knockback", "busy"])
        self.exit_resolver = exit_resolver
        self.friction = friction
        self.on_enter = on_enter

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Run the optional setup hook, then apply the launch velocity."""
        if self.on_enter is not None:
            self.on_enter(**kwargs)

        knockback_dir = kwargs.get("knockback_direction", 0)
        knockback_force = kwargs.get("knockback_force", 0)
        knockback_up = kwargs.get("knockback_up_force", 0)

        if knockback_dir != 0 and knockback_force > 0:
            self.entity.velocity.x = knockback_dir * knockback_force
        if knockback_up > 0:
            self.entity.velocity.y = -knockback_up

    def update(self, delta_time: float) -> Optional[str]:
        """Apply ground friction and resolve once the entity stops sliding."""
        if self.entity.on_surface["floor"]:
            lerp_velocity(self.entity, 0.0, self.friction, delta_time)
            if (
                abs(self.entity.velocity.x) < KNOCKBACK_STOP_SPEED
                and abs(self.entity.velocity.y) < KNOCKBACK_STOP_VERTICAL
            ):
                self.entity.velocity.x = 0.0
                return self.exit_resolver()
        return None


class StaggerState(State):
    """Stunned: stay locked until the stagger timer clears."""

    def __init__(
        self,
        entity: Any,
        exit_resolver: Callable[[], str | None],
        *,
        friction: float = 0.0,
        tags: Optional[list[str]] = None,
    ) -> None:
        super().__init__(entity, tags or ["stagger", "busy"])
        self.exit_resolver = exit_resolver
        self.friction = friction

    def update(self, delta_time: float) -> Optional[str]:
        """Apply ground friction and leave the state when the timer clears."""
        if self.friction > 0 and self.entity.on_surface["floor"]:
            lerp_velocity(self.entity, 0.0, self.friction, delta_time)
        if self.entity.stagger_timer <= 0:
            return self.exit_resolver()
        return None