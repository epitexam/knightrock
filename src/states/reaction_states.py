"""Shared reaction states (hurt / knockback / stagger / dizzy) for players and enemies.

These states were duplicated between ``player_states.py`` and
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

from collections.abc import Callable
from typing import Any, Final

from src.core.settings import Combat, Physics
from src.physics import lerp_velocity
from src.states.state_machine import State

#: Shared reaction-state vocabulary: ``ReactionComponent`` drives the state
#: machine with these names, and both state-name enums carry the same values
#: (``PlayerState``/``EnemyState``). Kept in sync by ``test_reaction_status``.
KNOCKBACK_STATE: Final[str] = "knockback"
STAGGER_STATE: Final[str] = "stagger"
DIZZY_STATE: Final[str] = "dizzy"

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
        tags: list[str] | None = None,
        on_enter: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["hurt", "busy"])
        self.exit_resolver = exit_resolver
        self.friction = friction
        self.on_enter = on_enter

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Run the optional setup hook with the transition kwargs."""
        if self.on_enter is not None:
            self.on_enter(**kwargs)

    def update(self, delta_time: float) -> str | None:
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
        max_duration: float = Combat.KNOCKBACK_MAX_DURATION,
        tags: list[str] | None = None,
        on_enter: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["knockback", "busy"])
        self.exit_resolver = exit_resolver
        self.friction = friction
        self.max_duration = max_duration
        self.on_enter = on_enter
        self._elapsed = 0.0
        self._launch_vx = 0.0

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        """Run the optional setup hook, then apply the launch velocity."""
        self._elapsed = 0.0
        if self.on_enter is not None:
            self.on_enter(**kwargs)

        knockback_dir = kwargs.get("knockback_direction", 0)
        knockback_force = kwargs.get("knockback_force", 0)
        knockback_up = kwargs.get("knockback_up_force", 0)

        if knockback_dir != 0 and knockback_force > 0:
            self.entity.velocity.x = knockback_dir * knockback_force
        if knockback_up != 0:
            self.entity.velocity.y = knockback_up
        self._launch_vx = self.entity.velocity.x

    def update(self, delta_time: float) -> str | None:
        """Apply ground friction and resolve once the entity stops sliding.

        A launch that never lands (pit fall) still releases after
        ``max_duration`` instead of locking the state machine forever.
        Airborne, the held direction steers the flight (directional
        influence), capped around the launch speed.
        """
        self._elapsed += delta_time
        if self.entity.on_surface["floor"]:
            lerp_velocity(self.entity, 0.0, self.friction, delta_time)
            if (
                abs(self.entity.velocity.x) < KNOCKBACK_STOP_SPEED
                and abs(self.entity.velocity.y) < KNOCKBACK_STOP_VERTICAL
            ):
                self.entity.velocity.x = 0.0
                return self.exit_resolver()
        else:
            self._apply_directional_influence(delta_time)
        if self._elapsed >= self.max_duration:
            return self.exit_resolver()
        return None

    def _apply_directional_influence(self, delta_time: float) -> None:
        """Steer an airborne launch toward the held direction (DI)."""
        move_axis = float(getattr(self.entity, "move_axis", 0.0) or 0.0)
        if move_axis == 0.0 or Combat.KNOCKBACK_DI_ACCEL <= 0:
            return
        cap = abs(self._launch_vx) + Combat.KNOCKBACK_DI_CAP
        vx = self.entity.velocity.x + move_axis * Combat.KNOCKBACK_DI_ACCEL * delta_time
        self.entity.velocity.x = max(-cap, min(cap, vx))


class StaggerState(State):
    """Stunned: stay locked until the stagger timer clears."""

    def __init__(
        self,
        entity: Any,
        exit_resolver: Callable[[], str | None],
        *,
        friction: float = 0.0,
        tags: list[str] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["stagger", "busy"])
        self.exit_resolver = exit_resolver
        self.friction = friction

    def update(self, delta_time: float) -> str | None:
        """Apply ground friction and leave the state when the timer clears."""
        if self.friction > 0 and self.entity.on_surface["floor"]:
            lerp_velocity(self.entity, 0.0, self.friction, delta_time)
        if self.entity.stagger_timer <= 0:
            return self.exit_resolver()
        return None


class DizzyState(State):
    """Stunned by consecutive perfect parries: locked until timer clears.

    Unlike stagger, this state is entered with a fixed duration and is
    cancellable by a new hit (the hit resets the timer via re-entry).
    """

    def __init__(
        self,
        entity: Any,
        exit_resolver: Callable[[], str | None],
        *,
        friction: float = 0.0,
        tags: list[str] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["dizzy", "busy"])
        self.exit_resolver = exit_resolver
        self.friction = friction

    def enter(self, previous: str | None = None, **kwargs: Any) -> None:
        duration = kwargs.get("duration", 0.0)
        if duration > 0:
            self.entity.stagger_timer = duration

    def update(self, delta_time: float) -> str | None:
        if self.friction > 0 and self.entity.on_surface["floor"]:
            lerp_velocity(self.entity, 0.0, self.friction, delta_time)
        if self.entity.stagger_timer <= 0:
            return self.exit_resolver()
        return None
