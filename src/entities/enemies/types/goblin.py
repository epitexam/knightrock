from src.combat.attack_data import GOBLIN_ATTACKS
from src.entities.enemies.schema import EnemyConfig
from src.entities.hurtbox_zones import HurtboxZoneDef

# P2 multi-hurtbox test data (debug tiers): head ×1.5 / torso ×1.0 /
# legs ×0.8, all concentric with the pushbox (P2 derivation = inflate
# re-centered, no per-zone offsets yet).
GOBLIN_HURTBOX_ZONES = (
    HurtboxZoneDef(name="head", inflate=(8.0, -28.0), mult=1.5),
    HurtboxZoneDef(name="torso", inflate=(0.0, 0.0), mult=1.0),
    HurtboxZoneDef(
        name="legs",
        inflate=(0.0, -28.0),
        mult=0.8,
        invuln_states=("airborne",),
    ),
)

GOBLIN_CONFIG = EnemyConfig(
    size=(36.0, 48.0),
    color=(60, 130, 60),
    health=60.0,
    attacks=GOBLIN_ATTACKS,
    attack_name="claw_swipe",
    hurtbox_zones=GOBLIN_HURTBOX_ZONES,
    chase_speed=120.0,
    vision_range=300.0,
    attack_range=60.0,
    patrol_interval=2.0,
    idle_duration=0.5,
    has_ai=True,
    pushable=True,
    super_armor=False,
    passive_friction=10.0,
    can_jump=True,
    jump_height=650.0,
    leap_speed_mult=1.6,
    parry_stun_threshold=2,
    parry_stun_duration=1.5,
)
