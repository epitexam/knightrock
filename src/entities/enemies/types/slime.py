from src.entities.enemies.schema import EnemyConfig
from src.combat.attack_data import SLIME_ATTACKS

SLIME_CONFIG = EnemyConfig(
    size=(32.0, 32.0),
    color=(80, 200, 220),
    health=40.0,
    attacks=SLIME_ATTACKS,
    attack_name="body_slam",
    chase_speed=80.0,
    vision_range=250.0,
    attack_range=50.0,
    patrol_interval=1.5,
    idle_duration=0.8,
    has_ai=True,
    pushable=True,
    super_armor=False,
    passive_friction=8.0,
)