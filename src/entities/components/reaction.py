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

from typing import Any, Protocol, runtime_checkable

import pygame
from pygame.math import Vector2

from src.combat.knockback import KnockbackConfig
from src.core.settings import Combat as CombatSettings

__all__ = ["ReactionComponent", "ReactionOwner", "compute_knockback_direction"]


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

    @property
    def combat(self) -> ReactionCombatPort: ...

    @property
    def state_machine(self) -> ReactionStatePort: ...


class ReactionComponent:
    """Turn an incoming hit into knockback, launch, and stagger reactions.

    Parameters
    ----------
    owner : ReactionOwner
        The narrow operated view; ``Entity`` satisfies it structurally.
    """

    def __init__(self, owner: ReactionOwner) -> None:
        self._owner = owner

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
        if knockback.mode == "fixed":
            owner.velocity.x = knockback.power[0]
            owner.velocity.y = knockback.power[1]
        else:
            direction = compute_knockback_direction(
                owner.hitbox.centerx, source_center_x, owner.facing_right
            )
            owner.velocity.x = knockback.power[0] * direction
            owner.velocity.y = knockback.power[1]

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
            "knockback",
            force=True,
            knockback_direction=direction,
            knockback_force=kb_power_x,
            knockback_up_force=kb_power_y,
        )
        # ``on_hit`` just armed ``is_hurt`` and ``hurt_timer``; only
        # ``reset_hurt_state`` clears both, so no stale timer is left behind.
        owner.combat.reset_hurt_state()
        return True

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
        owner.state_machine.change_state("stagger", force=True)
