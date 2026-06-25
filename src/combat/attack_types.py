"""
Data structures for attack definitions.
Moved from combat.py to break coupling (C3).
"""
from dataclasses import dataclass, field
from typing import List, Literal


@dataclass
class KnockbackConfig:
    power: tuple[float, float] = (250.0, -150.0)
    mode: Literal["from_attacker", "fixed"] = "from_attacker"


@dataclass
class AttackPhase:
    size: tuple[float, float]
    offset: tuple[float, float]
    damage: int
    duration: float
    reset_targets: bool = True
    knockback: KnockbackConfig = field(default_factory=KnockbackConfig)


@dataclass
class AttackSequence:
    phases: List[AttackPhase]
    cooldown: float
    lock_direction: bool = False