"""Per-entity components extracted from ``Entity`` (audit Phase 3 #2).

``Entity`` used to own both its kinematic state (velocity, surface
contacts) and its hit-reaction rules (knockback, heavy launch, stagger)
inline, alongside the already-composed ``Vitals`` and ``CombatComponent``.
This package finishes the composition: the movement and reaction
responsibilities live in dedicated components, wired into ``Entity``
exactly like ``vitals``/``combat``.
"""

from src.entities.components.movement import MovementComponent
from src.entities.components.reaction import ReactionComponent, compute_knockback_direction

__all__ = [
    "MovementComponent",
    "ReactionComponent",
    "compute_knockback_direction",
]
