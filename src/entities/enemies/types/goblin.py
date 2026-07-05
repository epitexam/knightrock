from src.combat.attack_data import GOBLIN_ATTACKS
from src.entities.enemies.schema import EnemyConfig


GOBLIN_CONFIG = EnemyConfig(
    size=(48.0, 48.0),
    color=(200, 50, 50),
    health=50.0,
    attacks=GOBLIN_ATTACKS,
    attack_name="claw_swipe",
)
