from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from src.combat.frame_data import AttackDefinition


@dataclass(frozen=True)
class EnemyConfig:
    """Reusable data needed to create an enemy type."""

    size: Sequence[float]
    color: Sequence[int]
    health: float
    attacks: Mapping[str, AttackDefinition]
    attack_name: str | None = None
    max_health: float | None = None
    hitbox_inflate: Sequence[float] = (0.0, 0.0)
    hurtbox_inflate: Sequence[float] = (0.0, 0.0)
    chase_speed: float = 120.0
    vision_range: float = 300.0
    attack_range: float = 60.0
    patrol_interval: float = 2.0
    idle_duration: float = 0.5
    has_ai: bool = True
    pushable: bool = True
    super_armor: bool = False
    passive_friction: float = 10.0
    # Per-type jump kit: only types with can_jump hop, and only while
    # chasing (wall ahead, player above). 0.0 height never jumps.
    can_jump: bool = False
    jump_height: float = 500.0
    jump_cooldown: float = 1.0
    # Sprint multiplier applied to the horizontal flight of gap leaps
    # (1.0 = no boost): this is what turns hops into real running jumps.
    leap_speed_mult: float = 1.0
    # State name (lowercase EnemyState key) -> sprite-sheet directory of
    # numbered PNG frames, e.g. {"idle": "assets/graphics/enemies/shell/idle"}.
    # States without an entry keep the last shown animation (Phase 2 #1).
    animations: Mapping[str, str] = field(default_factory=dict)
    # Parry-stun threshold: consecutive perfect parries needed to dizzy.
    # None = immune (e.g. dummy).  Set per enemy type in its config.
    parry_stun_threshold: int | None = None
    parry_stun_duration: float = 0.0
