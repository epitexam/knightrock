from src.entities.enemies.schema import EnemyConfig
from src.combat.frame_data import AttackDefinition, PhaseDefinition, HitProperties
from src.combat.knockback import KnockbackConfig
from src.combat.damage_types import DamageType

DUMMY_ATTACKS = {
    "test": AttackDefinition(
        phases=(
            PhaseDefinition(
                startup_frames=1,
                active_frames=1,
                recovery_frames=1,
                hitbox_size=(1.0, 1.0),
                hitbox_offset=(0.0, 0.0),
                hit=HitProperties(
                    damage=0,
                    knockback=KnockbackConfig(power=(0.0, 0.0)),
                    damage_type=DamageType.BLUNT,
                    stagger=0.0,
                ),
            ),
        ),
        cooldown=0.1,
        lock_direction=False,
    ),
}

DUMMY_CONFIG = EnemyConfig(
    size=(40.0, 48.0),
    color=(180, 180, 180),
    health=999.0,
    attacks=DUMMY_ATTACKS,
    attack_name="test",
    chase_speed=0.0,
    vision_range=0.0,
    attack_range=0.0,
    has_ai=False,
    pushable=False,
    super_armor=True,
    passive_friction=5.0,
)