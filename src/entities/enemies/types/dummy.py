from src.core.colors import Colors
from src.entities.enemies.schema import EnemyConfig


DUMMY_CONFIG = EnemyConfig(
    size=(48.0, 56.0),
    color=Colors.grey,
    health=500.0,
    attacks={},
    hitbox_inflate=(-8.0, 0.0),
    has_ai=False,
)
