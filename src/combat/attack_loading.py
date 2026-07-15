"""
Utility for loading attack definitions into a combat component.
"""

from collections.abc import Mapping

from src.combat.frame_data import AttackDefinition
from src.combat.combat_component import CombatComponent


def load_attacks(combat: CombatComponent, attacks: Mapping[str, AttackDefinition]) -> None:
    """Register a mapping of attack definitions into a combat component.

    Parameters
    ----------
    combat : CombatComponent
        The combat component to populate.
    attacks : Mapping[str, AttackDefinition]
        A dictionary-like object mapping attack names to their definitions.
    """
    for name, definition in attacks.items():
        combat.add_attack(name, definition)