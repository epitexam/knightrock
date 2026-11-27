"""Shared reaction states (hurt / knockback / stagger) for players and enemies.

These states were duplicated between ``player_states.py`` and
``enemy_states.py`` with only small differences.  The shared
logic is now parameterized by:

- ``exit_resolver``: a zero-argument callable returning the next state name
  (or ``None`` to stay) once the reaction completes.  Players resolve to
  ``ground_return``-style names; enemies resolve to ``"idle"``.
- ``on_enter``: optional callback invoked with the transition ``kwargs``,
  used for entity-specific setup (clearing the dash request, light knockback).
- ``tags``: state-machine tags preserved from the original classes.

What is *not* a parameter is how the push decays. The three states slow their
fighter with the same :func:`apply_reaction_drag`, so the distance a hit sends
its target depends on the hit, not on which reaction it happened to trigger.

Dizzy is the exception and is *not* shared: ``PlayerDizzyState`` and
``EnemyDizzyState`` are two near-identical classes in their own modules, each
subclassing :class:`State`. A shared ``DizzyState`` base used to sit here
alongside the other three; nothing ever subclassed it, so it was removed. They
also tick ``stagger_timer`` down in ``update`` where the three shared states
read it and let ``PhysicsSystem`` clean it up, so they are not a drop-in
subclassing exercise. ``DIZZY_STATE`` stays: the parry path and the overlay
both name the state through it.
"""

from collections.abc import Callable
from typing import Any, Final

from src.simulation.physics import apply_slide_friction, apply_velocity_friction
from src.simulation.settings import Combat, Physics
from src.simulation.states import state_names
from src.simulation.states.state_machine import EntityT, State, int_arg, number_arg

#: Shared reaction-state vocabulary: ``ReactionComponent`` drives the state
#: machine with these names, and both state-name enums carry the same values
#: (``PlayerState``/``EnemyState``). Kept in sync by ``test_reaction_status``.
KNOCKBACK_STATE: Final[str] = state_names.KNOCKBACK
STAGGER_STATE: Final[str] = state_names.STAGGER
DIZZY_STATE: Final[str] = state_names.DIZZY
# Horizontal speed (px/s) below which knockback is considered resolved.
KNOCKBACK_STOP_SPEED = 20.0
# Vertical speed (px/s) below which the launch is considered landed.
KNOCKBACK_STOP_VERTICAL = 1.0


def is_sliding(entity: Any) -> bool:
    """Whether a hit fighter is on the ground, as opposed to leaving it.

    The floor flag alone is one tick late: it is refreshed by the move, which
    runs after the state. A fighter launched upward still carries it on the
    tick of the launch, and the ground friction used to take an eighth of the
    launch speed before the feet had left the floor.
    """
    return bool(entity.on_surface["floor"]) and entity.velocity.y >= 0.0


def apply_reaction_drag(entity: Any, delta_time: float) -> None:
    """Bleed off the horizontal speed of a fighter reacting to a hit.

    Sliding, the ground grips it (:func:`apply_slide_friction`); airborne, the
    air barely slows it. See ``Physics.REACTION_*`` for the figures.
    """
    if is_sliding(entity):
        apply_slide_friction(
            entity, Physics.REACTION_SLIDE_FRICTION, Physics.REACTION_SLIDE_DRAG, delta_time
        )
    elif Physics.REACTION_AIR_DRAG > 0.0:
        apply_velocity_friction(entity, Physics.REACTION_AIR_DRAG, delta_time)


class HurtState(State[EntityT]):
    snapshot_fields: tuple[str, ...] = ()

    """Reaction to taking damage: wait for the hurt timer to clear."""

    def __init__(
        self,
        entity: EntityT,
        exit_resolver: Callable[[], str | None],
        *,
        tags: list[str] | None = None,
        on_enter: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["hurt", "busy"])
        self.exit_resolver = exit_resolver
        self.on_enter = on_enter

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        """Run the optional setup hook with the transition kwargs."""
        if self.on_enter is not None:
            self.on_enter(**kwargs)

    def update(self, delta_time: float) -> str | None:
        """Slow the push and leave the state once the hurt timer clears."""
        apply_reaction_drag(self.entity, delta_time)
        if not self.entity.combat.is_hurt:
            return self.exit_resolver()
        return None


class KnockbackState(State[EntityT]):
    snapshot_fields = ("max_duration", "_elapsed", "_launch_vx")

    """Strong launch: wait for the entity to land and slow down."""

    def __init__(
        self,
        entity: EntityT,
        exit_resolver: Callable[[], str | None],
        *,
        max_duration: float = Combat.KNOCKBACK_MAX_DURATION,
        tags: list[str] | None = None,
        on_enter: Callable[..., None] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["knockback", "busy"])
        self.exit_resolver = exit_resolver
        self.max_duration = max_duration
        self.on_enter = on_enter
        self._elapsed = 0.0
        self._launch_vx = 0.0

    def enter(self, previous: str | None = None, **kwargs: object) -> None:
        """Run the optional setup hook, then apply the launch velocity."""
        self._elapsed = 0.0
        if self.on_enter is not None:
            self.on_enter(**kwargs)

        knockback_dir = int_arg(kwargs, "knockback_direction", 0)
        knockback_force = number_arg(kwargs, "knockback_force", 0.0)
        knockback_up = number_arg(kwargs, "knockback_up_force", 0.0)

        if knockback_dir != 0 and knockback_force > 0:
            self.entity.velocity.x = knockback_dir * knockback_force
        if knockback_up != 0:
            self.entity.velocity.y = knockback_up
        self._launch_vx = self.entity.velocity.x

    def update(self, delta_time: float) -> str | None:
        """Slow the flight or the slide, and resolve once the entity stops sliding.

        A launch that never lands (pit fall) still releases after
        ``max_duration`` instead of locking the state machine forever.
        Airborne, the held direction steers the flight (directional
        influence), capped around the launch speed.
        """
        self._elapsed += delta_time
        apply_reaction_drag(self.entity, delta_time)
        if is_sliding(self.entity):
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
        move_axis = float(self.entity.move_axis)
        if move_axis == 0.0 or Combat.KNOCKBACK_DI_ACCEL <= 0:
            return
        cap = abs(self._launch_vx) + Combat.KNOCKBACK_DI_CAP
        vx = self.entity.velocity.x + move_axis * Combat.KNOCKBACK_DI_ACCEL * delta_time
        self.entity.velocity.x = max(-cap, min(cap, vx))


class StaggerState(State[EntityT]):
    snapshot_fields: tuple[str, ...] = ()

    """Stunned: stay locked until the stagger timer clears."""

    def __init__(
        self,
        entity: EntityT,
        exit_resolver: Callable[[], str | None],
        *,
        tags: list[str] | None = None,
    ) -> None:
        super().__init__(entity, tags or ["stagger", "busy"])
        self.exit_resolver = exit_resolver

    def update(self, delta_time: float) -> str | None:
        """Slow the push and leave the state when the timer clears."""
        apply_reaction_drag(self.entity, delta_time)
        if self.entity.stagger_timer <= 0:
            return self.exit_resolver()
        return None
