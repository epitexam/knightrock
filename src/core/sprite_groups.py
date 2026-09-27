from dataclasses import dataclass, field

import pygame


@dataclass
class SpriteGroups:
    """The world's sprite planes, split by how the renderer has to treat them.

    Three planes matter to a frame, and they differ in one property: whether
    the sprite moves.

    - ``static_sprites`` and ``fg_sprites`` hold the tile layers. They are
      built once when the level loads and never move, so the renderer culls
      them through a spatial index
      (:class:`~src.core.rendering.tile_chunk_index.TileChunkIndex`) instead
      of testing every tile against the camera sixty times a second. ``fg``
      is separate from the rest because it draws *last*, on top of
      everything else.
    - ``all_sprites`` holds everything that moves: the player, enemies,
      hazards, moving platforms, projectiles, the exit. Tens of sprites, so
      scanning it is cheap and stays exact.

    The tile layers are therefore **not** in ``all_sprites``. That is what
    makes the indexed cull pay off: leaving them there would force the
    renderer to walk all ~970 of them every frame just to discover it had
    already drawn them through the index. Anything that wants the whole world
    -- the debug overlay, the sprite counter -- chains the planes instead of
    reading one group, and ``tests/unit/test_tile_chunk_index.py`` asserts the
    partition is total so a sprite cannot go missing from a frame.
    """

    all_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    collision_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    moving_platforms: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    combat_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    entity_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    fx_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    hazard_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    projectile_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    fg_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    exit_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)

    static_sprites: pygame.sprite.Group = field(default_factory=pygame.sprite.Group)
    """The frozen tile layers that draw *under* the world (``Terrain``,
    ``BG``, ``Platforms``), in Tiled layer order. Excluded from
    ``all_sprites``; see the class docstring."""

    @property
    def every_sprite(self) -> tuple[pygame.sprite.Sprite, ...]:
        """Every drawable sprite, in the order a frame paints them.

        Only for consumers that genuinely want the whole world -- the debug
        overlay, the sprite counter. The draw path must not use it: it is an
        O(level) walk, which is the thing the tile index exists to avoid.
        """
        return (*self.static_sprites, *self.all_sprites, *self.fg_sprites)
