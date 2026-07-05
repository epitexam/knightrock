from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.combat.attack_types import AttackSequence


@dataclass(frozen=True)
class EnemyConfig:
    """Reusable data needed to create an enemy type."""

    size: Sequence[float]
    color: Sequence[int]
    health: float
    attacks: Mapping[str, AttackSequence]
    attack_name: str | None = None
    max_health: float | None = None
    hitbox_inflate: Sequence[float] = (0.0, 0.0)
    chase_speed: float = 120.0
    vision_range: float = 300.0
    attack_range: float = 60.0
    patrol_interval: float = 2.0
    idle_duration: float = 0.5
    has_ai: bool = True
    pushable: bool = True
    super_armor: bool = False
    passive_friction: float = 10.0
