"""
Builds game objects from parsed level data using registries for extensibility.
"""

import functools
import logging

import pygame

from src.core.colors import Colors
from src.core.settings import World
from src.core.sprites import Sprite, MovingPlatform, LevelExit
from src.core.hazards import OrbitingHazard, SpanHazard
from src.core.level.level_data import LevelData, ObjectData
from src.core.level.level_registry import Registry
from src.core.sprite_groups import SpriteGroups
from src.physics.hazard_damage import HazardDamageSystem
from src.entities.enemies.factory import create_enemy, is_enemy_type
from src.entities.player import Player

logger = logging.getLogger(__name__)

TILE_LAYER_HANDLERS: Registry = Registry("tile layer")
OBJECT_FACTORIES: Registry = Registry("object")


def _build_terrain(tiles, groups: SpriteGroups) -> None:
    """Create solid terrain sprites from tile layer tiles."""
    for x, y, surf in tiles:
        Sprite(
            pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
            surf=surf,
            groups=(groups.all_sprites, groups.collision_sprites),
        )


def _build_decor(tiles, groups: SpriteGroups, *, foreground: bool) -> None:
    """Create decorative sprites from tile layer tiles."""
    target = groups.fg_sprites if foreground else groups.all_sprites
    for x, y, surf in tiles:
        Sprite(
            pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
            surf=surf,
            groups=target,
        )


TILE_LAYER_HANDLERS.register("Terrain")(_build_terrain)
TILE_LAYER_HANDLERS.register("BG")(
    functools.partial(_build_decor, foreground=False))
TILE_LAYER_HANDLERS.register("Platforms")(
    functools.partial(_build_decor, foreground=False)
)
TILE_LAYER_HANDLERS.register("FG")(
    functools.partial(_build_decor, foreground=True))


def _parse_waypoints(obj: ObjectData) -> list[tuple[float, float]]:
    """
    Extract waypoints from an object's points or properties.

    Prefers the 'points' attribute, then the 'waypoints' string property,
    and falls back to an implied end point from 'end_x'/'end_y' or a default.
    """
    if obj.points:
        return obj.points
    waypoints_str = obj.properties.get("waypoints", "")
    if waypoints_str:
        points = []
        for point in waypoints_str.split(";"):
            x_str, y_str = point.split(",")
            points.append((float(x_str), float(y_str)))
        return points
    end_x = float(obj.properties.get("end_x", obj.x + 100))
    end_y = float(obj.properties.get("end_y", obj.y))
    return [(obj.x, obj.y), (end_x, end_y)]


def _sized_surface(obj: ObjectData, color) -> pygame.Surface:
    """Create a surface for a moving platform with a minimum thickness."""
    min_thickness = World.TILE_SIZE // 2
    width, height = obj.width, obj.height
    if height < min_thickness:
        width, height = max(width, min_thickness), min_thickness
    elif width < min_thickness:
        width, height = min_thickness, max(height, min_thickness)
    surf = pygame.Surface((width, height))
    surf.fill(color)
    return surf


def _build_moving_platform(obj: ObjectData, groups: SpriteGroups) -> None:
    """Create a MovingPlatform from object data and add it to groups."""
    surf = _sized_surface(obj, Colors.gold)
    speed = float(obj.properties.get("speed", 100))
    platform = MovingPlatform(
        (obj.x, obj.y),
        surf,
        _parse_waypoints(obj),
        speed,
        (groups.all_sprites, groups.collision_sprites),
    )
    groups.moving_platforms.add(platform)


def _build_span_hazard(obj: ObjectData, groups: SpriteGroups) -> None:
    """Create a linearly moving hazard (saw)."""
    surf = pygame.Surface((max(obj.width, 1), max(obj.height, 1)))
    surf.fill(Colors.red)
    speed = float(obj.properties.get("speed", 100))
    flip = bool(obj.properties.get("flip", False))
    damage = float(obj.properties.get(
        "damage", HazardDamageSystem.DEFAULT_DAMAGE))
    hazard = SpanHazard(
        (obj.x, obj.y), surf, speed, flip, groups.all_sprites, damage=damage
    )
    groups.hazard_sprites.add(hazard)


def _build_orbiting_hazard(obj: ObjectData, groups: SpriteGroups) -> None:
    """Create a circularly moving hazard (spike)."""
    size = max(obj.width, obj.height, 1)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(surf, Colors.red, (size / 2, size / 2), size / 2)
    radius = float(obj.properties.get("radius", 0))
    start_angle = float(obj.properties.get("start_angle", 0))
    end_angle = float(obj.properties.get("end_angle", 360))
    speed = float(obj.properties.get("speed", 50))
    damage = float(obj.properties.get(
        "damage", HazardDamageSystem.DEFAULT_DAMAGE))
    hazard = OrbitingHazard(
        (obj.x, obj.y),
        surf,
        radius,
        start_angle,
        end_angle,
        speed,
        groups.all_sprites,
        damage=damage,
    )
    groups.hazard_sprites.add(hazard)


def _build_static_hazard(obj: ObjectData, groups: SpriteGroups) -> None:
    """Create an immobile hazard (e.g. floor spikes) from a placed image."""
    surf = obj.image
    if surf is None:
        surf = pygame.Surface((max(obj.width, 1), max(obj.height, 1)))
        surf.fill(Colors.red)
    damage = float(obj.properties.get(
        "damage", HazardDamageSystem.DEFAULT_DAMAGE))
    hazard = SpanHazard(
        (obj.x, obj.y), surf, 0.0, False, groups.all_sprites, damage=damage
    )
    groups.hazard_sprites.add(hazard)


def _build_exit(obj: ObjectData, groups: SpriteGroups) -> None:
    """Create the level exit flag."""
    groups.exit_sprites.add(LevelExit((obj.x, obj.y), groups.all_sprites))


OBJECT_FACTORIES.register("helicopter")(_build_moving_platform)
OBJECT_FACTORIES.register("boat")(_build_moving_platform)
OBJECT_FACTORIES.register("saw")(_build_span_hazard)
OBJECT_FACTORIES.register("spike")(_build_orbiting_hazard)
OBJECT_FACTORIES.register("floor_spike")(_build_static_hazard)
OBJECT_FACTORIES.register("flag")(_build_exit)


class WorldBuilder:
    """
    Constructs the game world from parsed LevelData.

    It processes tile layers through registered handlers and object layers
    through registered factories. Unknown objects are either spawned as
    static images (if they have one) or logged as ignored.
    """

    def __init__(self, level_data: LevelData):
        self.level_data = level_data

    def build(self, groups: SpriteGroups, input_manager):
        """
        Build all sprites and return the player instance.

        Args:
            groups: Container for all sprite groups.
            input_manager: Input manager to pass to the player.

        Returns:
            The Player instance, or None if not found.
        """
        for layer in self.level_data.tile_layers.values():
            TILE_LAYER_HANDLERS.dispatch(layer.name, layer.tiles, groups)

        player = self._build_player(groups, input_manager)
        if player is None:
            raise ValueError(
                "Level has no 'player' object. Every level must define a "
                "player spawn object in one of its object layers."
            )

        for layer in self.level_data.object_layers.values():
            if layer.name == "Data":
                continue
            for obj in layer.objects:
                self._build_object(obj, groups, player)

        return player

    def _build_player(self, groups: SpriteGroups, input_manager):
        """Locate the player object and instantiate it."""
        for layer in self.level_data.object_layers.values():
            for obj in layer.objects:
                if obj.name == "player":
                    player = Player(
                        (obj.x, obj.y),
                        groups.all_sprites,
                        groups.collision_sprites,
                        groups.moving_platforms,
                        input_manager,
                    )
                    groups.combat_sprites.add(player)
                    groups.entity_sprites.add(player)
                    return player
        return None

    def _build_object(self, obj: ObjectData, groups: SpriteGroups, player) -> None:
        """
        Build a single object from an object layer.

        Handles enemies (via factory), registered object types,
        and static images.
        """
        if obj.name == "player":
            return
        if is_enemy_type(obj.name):
            entity = create_enemy(
                obj.name,
                pos=(obj.x, obj.y),
                groups=(groups.all_sprites,),
                collision_sprites=groups.collision_sprites,
                player_reference=player,
            )
            groups.combat_sprites.add(entity)
            groups.entity_sprites.add(entity)
        elif OBJECT_FACTORIES.has(obj.name):
            OBJECT_FACTORIES.dispatch(obj.name, obj, groups)
        elif obj.image is not None:
            Sprite(pos=(obj.x, obj.y), surf=obj.image,
                   groups=groups.all_sprites)
        else:
            logger.debug(
                "Object '%s' has no factory or image, ignored", obj.name)
