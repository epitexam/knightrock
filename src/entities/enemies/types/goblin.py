from src.entities.enemies.schema import EnemyConfig
from src.combat.attack_data import GOBLIN_ATTACKS

GOBLIN_CONFIG = EnemyConfig(
    size=(36.0, 48.0),
    color=(60, 130, 60),
    health=60.0,
    attacks=GOBLIN_ATTACKS,
    attack_name="claw_swipe",
    chase_speed=120.0,
    vision_range=300.0,
    attack_range=60.0,
    patrol_interval=2.0,
    idle_duration=0.5,
    has_ai=True,
    pushable=True,
    super_armor=False,
    passive_friction=10.0,
)