"""ReactionComponent: hit-reaction rules for an entity.

Extracted from ``Entity`` (audit Phase 3 #2) so knockback, heavy launch, and
stagger live in a dedicated component wired in like ``vitals``/``combat``
instead of sitting inline on the entity aggregate (audit F2.2).

The component owns the *rules*, not the state: velocity and contacts belong
to movement, health and status timers to vitals, hurt state to combat, and
states to the state machine. It operates through the narrow
:class:`ReactionOwner` view. ``Entity.receive_damage`` stays the public entry
point (``Player`` overrides it for blocking).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Protocol, runtime_checkable

import pygame
from pygame.math import Vector2

from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings
from src.core.settings import Guard as GuardSettings
from src.core.settings import ReactionMark
from src.states.reaction_states import KNOCKBACK_STATE, STAGGER_STATE

__all__ = [
    "ReactionComponent",
    "ReactionKind",
    "ReactionOwner",
    "ReactionStatus",
    "VELOCITY_KINDS",
    "compute_knockback_direction",
]


class ReactionKind(Enum):
    PUSH = "push"
    LAUNCH = "launch"
    STAGGER = "stagger"
    GUARDED = "guarded"
    PARRIED = "parried"


#: Kinds that carry an applied velocity push. The debug overlay paints these
#: vectors red while the status is fresh *or* while the knockback state still
#: carries the entity; stagger only locks the state machine without an impulse,
#: so it stays a locomotion-colored vector.
VELOCITY_KINDS: Final[frozenset[ReactionKind]] = frozenset(
    {ReactionKind.PUSH, ReactionKind.LAUNCH, ReactionKind.GUARDED}
)


@dataclass(frozen=True)
class ReactionStatus:
    """Typed record of the last applied hit reaction.

    Attributes
    ----------
    kind : ReactionKind
        Which reaction fired (push, launch, stagger, blocked push).
    magnitude : float
        Full impulse magnitude in px/s (0.0 for stagger).
    direction : float
        Horizontal push direction: 1.0 right, -1.0 left (0.0 for stagger).

    Render/debug data: read by the overlay, never snapshotted, never in
    goldens.
    """

    kind: ReactionKind
    magnitude: float
    direction: float


def compute_knockback_direction(
    hitbox_centerx: float,
    source_center_x: float | None,
    facing_right: bool,
) -> float:
    """Compute the horizontal direction of a knockback impulse.

    Parameters
    ----------
    hitbox_centerx : float
        The center X coordinate of the receiving entity.
    source_center_x : float | None
        The center X coordinate of the damage source.
    facing_right : bool
        The current facing direction of the entity.

    Returns
    -------
    float
        1.0 for right, -1.0 for left.
    """
    if source_center_x is not None:
        return 1.0 if hitbox_centerx >= source_center_x else -1.0
    return 1.0 if facing_right else -1.0


class ReactionCombatPort(Protocol):
    """Combat operations available to Reaction."""

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None: ...

    def reset_hurt_state(self) -> None: ...


class ReactionStatePort(Protocol):
    """State operation available to Reaction."""

    def change_state(self, name: str, force: bool = False, **kwargs: Any) -> None: ...


@runtime_checkable
class ReactionOwner(Protocol):
    """Narrow owner view operated on by ReactionComponent."""

    velocity: Vector2
    hitbox: pygame.FRect
    facing_right: bool
    is_dead: bool
    stagger_timer: float
    super_armor: bool
    super_armor_count: int
    # Render-only freshness of the last reaction; decayed in Entity.update,
    # armed here and never snapshotted.
    reaction_age: float

    @property
    def combat(self) -> ReactionCombatPort: ...

    @property
    def state_machine(self) -> ReactionStatePort: ...


class ReactionComponent:
    """Turn an incoming hit into knockback, launch, and stagger reactions.

    Owns the *cause* of a reaction (``status``: what hit, how hard, which
    way, refreshed ``reaction_age``); the state machine owns the *category in
    progress*. Both are written at the same sites in the same tick.

    Parameters
    ----------
    owner : ReactionOwner
        The narrow operated view; ``Entity`` satisfies it structurally.
    """

    def __init__(self, owner: ReactionOwner) -> None:
        self._owner = owner
        self.status: ReactionStatus | None = None

    def _arm(self, kind: ReactionKind, magnitude: float, direction: float) -> None:
        """Record the reaction cause and refresh the render-only freshness age."""
        self.status = ReactionStatus(kind=kind, magnitude=magnitude, direction=direction)
        self._owner.reaction_age = ReactionMark.DURATION

    def apply_knockback(
        self,
        knockback: KnockbackConfig,
        source_center_x: float | None,
    ) -> None:
        """Apply knockback velocity based on the configuration and source position.

        Parameters
        ----------
        knockback : KnockbackConfig
            Configuration for the push effect.
        source_center_x : float | None
            X-coordinate of the damage source for knockback direction.
        """
        if knockback.power == (0.0, 0.0):
            return

        owner = self._owner
        direction: float
        if knockback.mode == "fixed":
            direction = 1.0 if knockback.power[0] >= 0.0 else -1.0
            owner.velocity.x = knockback.power[0]
            owner.velocity.y = knockback.power[1]
        else:
            direction = compute_knockback_direction(
                owner.hitbox.centerx, source_center_x, owner.facing_right
            )
            owner.velocity.x = knockback.power[0] * direction
            owner.velocity.y = knockback.power[1]
        self._arm(
            ReactionKind.PUSH,
            Vector2(knockback.power[0], knockback.power[1]).length(),
            direction,
        )

    def handle_heavy_knockback(
        self,
        knockback: KnockbackConfig,
        source_center_x: float | None,
    ) -> bool:
        """Trigger the launch state for knockback at or above the heavy threshold.

        The full vector magnitude is used so upward launches and combined
        diagonal impulses are classified consistently.

        Parameters
        ----------
        knockback : KnockbackConfig
            Configuration for the push effect.
        source_center_x : float | None
            X-coordinate of the damage source for knockback direction.

        Returns
        -------
        bool
            ``True`` when the heavy-knockback launch state was entered.
        """
        owner = self._owner
        kb_power_x, kb_power_y = knockback.power
        magnitude = Vector2(kb_power_x, kb_power_y).length()
        if magnitude < CombatSettings.HEAVY_KNOCKBACK_THRESHOLD:
            return False

        # Cancel an active action before selecting knockback as the definitive
        # reaction. This avoids a simultaneous hurt/knockback state.
        owner.combat.on_hit(interrupt=True)
        direction = compute_knockback_direction(
            owner.hitbox.centerx, source_center_x, owner.facing_right
        )
        owner.state_machine.change_state(
            KNOCKBACK_STATE,
            force=True,
            knockback_direction=direction,
            knockback_force=kb_power_x,
            knockback_up_force=kb_power_y,
        )
        # ``on_hit`` just armed ``is_hurt`` and ``hurt_timer``; only
        # ``reset_hurt_state`` clears both, so no stale timer is left behind.
        owner.combat.reset_hurt_state()
        self._arm(ReactionKind.LAUNCH, magnitude, direction)
        return True

    def note_guard_push(
        self,
        knockback: KnockbackConfig,
        source_center_x: float | None,
        parried: bool = False,
    ) -> None:
        if knockback.mode == "fixed":
            direction = 1.0 if knockback.power[0] >= 0.0 else -1.0
        else:
            direction = compute_knockback_direction(
                self._owner.hitbox.centerx, source_center_x, self._owner.facing_right
            )
        if parried:
            self._arm(ReactionKind.PARRIED, 0.0, direction)
            return
        push = abs(knockback.power[0]) * GuardSettings.PUSH_FACTOR
        self._arm(ReactionKind.GUARDED, push, direction)

    def stagger(self, duration: float) -> None:
        """Apply stagger, handling super armor and stunlock protection.

        Super armor is consumed after ``SUPER_ARMOR_THRESHOLD`` hits.  If the
        entity has super armor and the threshold is not reached, no stagger is
        applied.

        Parameters
        ----------
        duration : float
            The duration of the stagger in seconds.
        """
        owner = self._owner
        if owner.is_dead or owner.stagger_timer > 0:
            return

        if owner.super_armor:
            owner.super_armor_count += 1
            if owner.super_armor_count < CombatSettings.SUPER_ARMOR_THRESHOLD:
                return
            owner.super_armor = False

        owner.stagger_timer = duration
        owner.combat.reset_hurt_state()
        owner.state_machine.change_state(STAGGER_STATE, force=True)
        self._arm(ReactionKind.STAGGER, 0.0, 0.0)
