"""ReactionComponent: hit-reaction rules for an entity.

Extracted from ``Entity`` (audit Phase 3 #2) so knockback, heavy launch, and
stagger live in a dedicated component wired in like ``vitals``/``combat``
instead of sitting inline on the entity aggregate (audit F2.2).

Propriété des données (RF-3) — le composant possède les *règles*, pas l'état :

=================== ============ ============================ ==================== ===================
Donnée             Propriétaire Écrivains autorisés           Reset                Snapshot
=================== ============ ============================ ==================== ===================
``velocity``       Movement     Reaction (knockback), états,  ``Movement.stop``    oui (EntitySnapshot)
                               locomotion
``on_surface``     Movement     physics/collisions            par tick            oui
``health/is_dead`` Vitals       ``apply_damage`` via           ``Vitals.reset``    oui (vitals)
                               ``receive_damage``
``stagger_timer``  Vitals       Reaction.stagger, tick vitals  ``Vitals.reset`` /  oui (vitals)
                               (décroissance)                 expiration
``super_armor*``   Vitals       Reaction.stagger,              ``Vitals.reset`` /  oui (vitals)
                               ``break_super_armor``          seuil
``is_hurt/timer``  Combat       ``on_hit``/``reset_hurt_state`` ``reset``/``reset_  oui (combat)
                               (Reaction ne fait que         ``hurt_state``
                               demander via ces ops)
``juggle/OTG``     Entity       ``set_juggle``/``_tick_juggle`` landing/reset      oui (extra)
``états``          StateMachine états + interrupts            ``change_state``     oui (state_machine)
=================== ============ ============================ ==================== ===================

Le composant ne reçoit qu'une vue étroite (:class:`ReactionOwner`) :
vélocité/géométrie en lecture-écriture ciblée, timers via ``vitals``
délégués, réactions via ``combat`` (``on_hit``/``reset_hurt_state``) et
``state_machine.change_state``. ``Entity.receive_damage`` reste l'entrée
publique (``Player`` la surcharge pour le blocage).
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
    """Opérations combat autorisées à Reaction (RF-3)."""

    def on_hit(self, duration: float | None = None, interrupt: bool = True) -> None: ...

    def reset_hurt_state(self) -> None: ...


class ReactionStatePort(Protocol):
    """Opération état autorisée à Reaction (RF-3)."""

    def change_state(self, name: str, force: bool = False, **kwargs: Any) -> None: ...


@runtime_checkable
class ReactionOwner(Protocol):
    """Vue étroite opérée par ReactionComponent (RF-3).

    Ni l'Entity entière recopiée ni couplage large : uniquement les
    opérations nécessaires (géométrie, vélocité, timers délégués,
    réactions combat/états).
    """

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
        Vue étroite opérée (vélocité, géométrie, timers, combat, états).
        ``Entity`` la satisfait structurellement ; les tests peuvent
        fournir un double étroit sans Entity complète.
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
        # Opération métier (RF-3) : ``on_hit`` vient d'armer ``is_hurt`` ET
        # ``hurt_timer`` ; une écriture directe ``is_hurt = False`` laisserait
        # un timer stale qui ne décrémente jamais (``update`` ne tick que si
        # ``is_hurt``). ``reset_hurt_state`` nettoie les deux, comme en
        # ``stagger`` ci-dessous — le knockback reste la réaction définitive.
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
