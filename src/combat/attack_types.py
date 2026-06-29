"""
Data structures for attack definitions.
"""
from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class KnockbackConfig:
    """Represent a KnockbackConfig."""
    power: tuple[float, float] = (250.0, -150.0)
    mode: Literal["from_attacker", "fixed"] = "from_attacker"


@dataclass
class AttackPhase:
    """Represent a AttackPhase."""
    size: tuple[float, float]
    offset: tuple[float, float]
    damage: int
    duration: float
    reset_targets: bool = True
    knockback: KnockbackConfig = field(default_factory=KnockbackConfig)

    damage_type: str = "slash"
    stagger: float = 0.0
    super_armor_break: bool = False
    is_finisher: bool = False


@dataclass
class AttackSequence:
    """Represent a AttackSequence."""
    phases: List[AttackPhase]
    cooldown: float
    lock_direction: bool = False
    combo_reset: bool = False
    chargeable: bool = False
    max_charge_time: float = 1.0
