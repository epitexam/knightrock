from collections.abc import Mapping

from src.combat.attack_types import AttackSequence
from src.combat.combat import CombatComponent


def load_attacks(combat: CombatComponent, attacks: Mapping[str, AttackSequence]) -> None:
    for name, sequence in attacks.items():
        combat.add_attack(name, sequence)