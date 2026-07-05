from collections.abc import Sequence
from typing import Any

from pygame.sprite import Group

from src.entities.enemies.configs import ENEMY_CONFIGS
from src.entities.enemies.enemy import Enemy


def is_enemy_type(name: str) -> bool:
    """Return whether an enemy config exists for the given type name."""
    return name in ENEMY_CONFIGS


def create_enemy(
    name: str,
    pos: Sequence[float],
    groups: Group | Sequence[Group],
    collision_sprites: Group,
    player_reference: Any = None,
) -> Enemy:
    """Create an enemy from the shared enemy registry."""
    config = ENEMY_CONFIGS[name]
    return Enemy(
        pos=pos,
        groups=groups,
        collision_sprites=collision_sprites,
        player_reference=player_reference,
        config=config,
    )
