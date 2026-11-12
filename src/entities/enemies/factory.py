"""Building an enemy from its configuration."""

from collections.abc import Sequence
from dataclasses import replace

from pygame.math import Vector2
from pygame.sprite import Group

from src.entities.enemies.enemy import Enemy, PlayerReference
from src.entities.enemies.schema import EnemyConfig
from src.physics.spatial_hash import SpatialHash


def create_enemy(
    name: str,
    pos: Sequence[float] | Vector2,
    groups: Group | Sequence[Group],
    collision_sprites: Group,
    player_reference: PlayerReference | None = None,
    config: EnemyConfig | None = None,
    spatial_hash: SpatialHash | None = None,
    reverse: bool | None = None,
) -> Enemy:
    """Create the enemy called ``name``.

    Parameters
    ----------
    name : str
        The enemy type (``"goblin"``, ``"dummy"``...), shown in the debug card.
    pos : Sequence[float] | Vector2
        Starting top-left position, normalized to a tuple of floats.
    groups : Group | Sequence[Group]
        Sprite group(s) to add this enemy to.
    collision_sprites : Group
        Group of sprites that block movement.
    player_reference : PlayerReference | None
        Reference to the player entity for AI targeting.
    config : EnemyConfig | None
        The configuration to build from. A level passes the one from the
        bundle it was given; without one, the shipped ``enemies.json`` entry
        for ``name`` is used -- never a copy kept in code (audit C4).
    spatial_hash : SpatialHash | None
        Shared collision grid covering ``collision_sprites``, so a
        runtime-spawned enemy is wired for O(1) neighbour lookups at birth.
    reverse : bool | None
        Authored patrol direction; ``None`` keeps the coin toss.

    Raises
    ------
    KeyError
        If no ``config`` is given and ``enemies.json`` has no ``name``.
    """
    if config is None:
        # Local: the data layer imports the enemy schema from this package.
        from src.data.provider import shipped_gameplay_data

        config = shipped_gameplay_data().enemies[name]
    if reverse is not None:
        config = replace(config, reverse=reverse)
    return Enemy(
        pos=(float(pos[0]), float(pos[1])),
        groups=groups,
        collision_sprites=collision_sprites,
        player_reference=player_reference,
        config=config,
        enemy_type=name,
        spatial_hash=spatial_hash,
    )
