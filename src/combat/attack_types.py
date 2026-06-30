""""
Data structures for attack definitions and configurations.
"""
from dataclasses import dataclass, field
from typing import List, Literal
from src.combat.damage_types import DamageType

@dataclass
class KnockbackConfig:
    """Configuration for knockback effects applied on hit."""
    power: tuple[float, float] = (250.0, -150.0)
    mode: Literal["from_attacker", "fixed"] = "from_attacker"

@dataclass
class AttackPhase:
    """Defines a single phase of an attack sequence."""
    size: tuple[float, float]
    offset: tuple[float, float]
    damage: int
    duration: float
    reset_targets: bool = True
    knockback: KnockbackConfig = field(default_factory=KnockbackConfig)
    damage_type: DamageType = DamageType.SLASH
    stagger: float = 0.0
    super_armor_break: bool = False
    is_finisher: bool = False

@dataclass
class AttackSequence:
    """Defines a complete attack sequence containing multiple phases."""
    phases: List[AttackPhase]
    cooldown: float
    lock_direction: bool = False
    combo_reset: bool = False
    chargeable: bool = False
    max_charge_time: float = 1.0