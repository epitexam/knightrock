from collections.abc import Sequence
from typing import Any

from pygame.math import Vector2
from pygame.sprite import Group

from src.entities.enemies.configs import ENEMY_CONFIGS
from src.entities.enemies.enemy import Enemy, PlayerReference
from src.entities.enemies.schema import EnemyConfig


def is_enemy_type(name: str) -> bool:
    """Check if an enemy config exists for the given type name.

    Parameters
    ----------
    name : str
        The enemy type name to check.

    Returns
    -------
    bool
        True if an enemy config exists for the given name.
    """
    return name in ENEMY_CONFIGS


def create_enemy(
    name: str,
    pos: Sequence[float] | Vector2,
    groups: Group | Sequence[Group],
    collision_sprites: Group,
    player_reference: PlayerReference | None = None,
) -> Enemy:
    """Create an enemy from the shared enemy registry.

    This is the official way to instantiate enemies. It uses the factory
    pattern with data-driven configuration from ENEMY_CONFIGS.

    Parameters
    ----------
    name : str
        The enemy type name (e.g., "goblin", "dummy", "slime").
    pos : Sequence[float] | Vector2
        Starting top-left position. Normalized to a tuple of floats
        before being handed to :class:`Enemy`.
    groups : Group | Sequence[Group]
        Sprite group(s) to add this enemy to.
    collision_sprites : Group
        Group of sprites that block movement.
    player_reference : PlayerReference | None
        Reference to the player entity for AI targeting.

    Returns
    -------
    Enemy
        A new enemy instance configured according to the specified config.

    Raises
    ------
    KeyError
        If the enemy type name is not found in ENEMY_CONFIGS.
    """
    config = ENEMY_CONFIGS[name]
    spawn_pos = (float(pos[0]), float(pos[1]))
    return Enemy(
        pos=spawn_pos,
        groups=groups,
        collision_sprites=collision_sprites,
        player_reference=player_reference,
        config=config,
    )
