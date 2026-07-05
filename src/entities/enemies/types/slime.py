from src.combat.attack_data import SLIME_ATTACKS
from src.entities.enemies.schema import EnemyConfig


SLIME_CONFIG = EnemyConfig(
    size=(40.0, 32.0),
    color=(80, 180, 90),
    health=30.0,
    attacks=SLIME_ATTACKS,
    attack_name="body_slam",
    hitbox_inflate=(-4.0, 0.0),
    chase_speed=80.0,
    vision_range=220.0,
    attack_range=44.0,
    patrol_interval=1.4,
    idle_duration=0.8,
)
