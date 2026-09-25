"""
Builds game objects from parsed level data using registries for extensibility.
"""

import functools
import logging
from collections.abc import Sequence

import pygame

from src.core.colors import Colors
from src.core.hazards import OrbitingHazard, SpanHazard, build_hazard_animator
from src.core.input.input_manager import InputManager
from src.core.level.level_data import LevelData, ObjectData
from src.core.level.level_registry import Registry
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.settings import World
from src.core.sprite_groups import SpriteGroups
from src.core.sprites import LevelExit, MovingPlatform, Sprite
from src.data.provider import GameplayData
from src.entities.enemies.factory import create_enemy, is_enemy_type
from src.entities.player import Player

logger = logging.getLogger(__name__)

TILE_LAYER_HANDLERS: Registry = Registry("tile layer")
OBJECT_FACTORIES: Registry = Registry("object")

#: Tiled tile layer as ``(x, y, surface)`` triples.
TileList = Sequence[tuple[int, int, pygame.Surface]]


def _build_terrain(tiles: TileList, groups: SpriteGroups) -> None:
    """Create solid terrain sprites from tile layer tiles."""
    for x, y, surf in tiles:
        Sprite(
            pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
            surf=surf,
            groups=(groups.all_sprites, groups.collision_sprites),
        )


def _build_decor(tiles: TileList, groups: SpriteGroups, *, foreground: bool) -> None:
    """Create decorative sprites from tile layer tiles."""
    target = groups.fg_sprites if foreground else groups.all_sprites
    for x, y, surf in tiles:
        Sprite(
            pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
            surf=surf,
            groups=target,
        )


def _build_one_way_platforms(tiles: TileList, groups: SpriteGroups) -> None:
    """Create one-way platform tiles: solid on top, pass-through elsewhere.

    An entity standing on top is supported (floor contact); jumping from
    below or walking into the side phases through, which is what a Tiled
    "Platforms" layer means in a platformer.
    """
    for x, y, surf in tiles:
        sprite = Sprite(
            pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
            surf=surf,
            groups=(groups.all_sprites, groups.collision_sprites),
        )
        sprite.one_way = True


TILE_LAYER_HANDLERS.register("Terrain")(_build_terrain)
TILE_LAYER_HANDLERS.register("BG")(functools.partial(_build_decor, foreground=False))
TILE_LAYER_HANDLERS.register("Platforms")(_build_one_way_platforms)
TILE_LAYER_HANDLERS.register("FG")(functools.partial(_build_decor, foreground=True))


def _explicit_waypoints(obj: ObjectData) -> list[tuple[float, float]] | None:
    """
    Waypoints authored on the object itself, or None when absent.

    Prefers the 'points' attribute, then the 'waypoints' string property,
    then 'end_x'/'end_y'.  When None, the object rectangle is the path.
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
    if "end_x" in obj.properties or "end_y" in obj.properties:
        end_x = float(obj.properties.get("end_x", obj.x))
        end_y = float(obj.properties.get("end_y", obj.y))
        return [(obj.x, obj.y), (end_x, end_y)]
    return None


def _rect_path(obj: ObjectData) -> tuple[pygame.math.Vector2, pygame.math.Vector2]:
    """The object rectangle's centre line: the full back-and-forth range.

    The rectangle drawn in Tiled is the travel distance, not the sprite:
    horizontal when the rectangle is at least as wide as tall, vertical
    otherwise, running edge to edge through the rectangle's middle.
    """
    centre_x = obj.x + obj.width / 2
    centre_y = obj.y + obj.height / 2
    if obj.width >= obj.height:
        return (
            pygame.math.Vector2(obj.x, centre_y),
            pygame.math.Vector2(obj.x + obj.width, centre_y),
        )
    return (
        pygame.math.Vector2(centre_x, obj.y),
        pygame.math.Vector2(centre_x, obj.y + obj.height),
    )


def _build_moving_platform(obj: ObjectData, groups: SpriteGroups) -> None:
    """Create a MovingPlatform patrolling the object rectangle.

    The Tiled rectangle is the travel range (back and forth), not the
    platform: the pad is a small surface launched at the rectangle's
    centre, then patrolling between the rectangle's ends at the 'speed'
    property (default 100 px/s).  Pad size: 'platform_width'/
    'platform_height' properties, default 2 tiles x half a tile.
    """
    half_tile = World.TILE_SIZE // 2
    width = max(float(obj.properties.get("platform_width", World.TILE_SIZE * 2)), half_tile)
    height = max(float(obj.properties.get("platform_height", half_tile)), half_tile)
    surf = pygame.Surface((width, height))
    surf.fill(Colors.gold)
    speed = float(obj.properties.get("speed", 100))
    half = pygame.math.Vector2(width / 2, height / 2)
    start, end = _rect_path(obj)
    waypoints = _explicit_waypoints(obj)
    if waypoints is None:
        # Waypoints are top-left targets: offset them so the pad's *centre*
        # travels the rectangle from end to end.
        waypoint_a = (start.x - half.x, start.y - half.y)
        waypoint_b = (end.x - half.x, end.y - half.y)
        waypoints = [waypoint_a, waypoint_b]
    middle = start.lerp(end, 0.5)
    platform = MovingPlatform(
        (middle.x - half.x, middle.y - half.y),
        surf,
        waypoints,
        speed,
        (groups.all_sprites, groups.collision_sprites),
        collision_sprites=groups.collision_sprites,
    )
    groups.moving_platforms.add(platform)


def _build_span_hazard(obj: ObjectData, groups: SpriteGroups) -> None:
    """Create a linearly moving hazard (saw) patrolling the object rectangle.

    The Tiled rectangle is the travel range, not the hazard: the saw sprite
    launches at the rectangle's centre and sweeps the full range back and
    forth at the 'speed' property (default 100 px/s).  Sprite size: 'size'
    property, else the animation's natural frame size, else one tile.
    """
    speed = float(obj.properties.get("speed", 100))
    flip = bool(obj.properties.get("flip", False))
    damage = float(obj.properties.get("damage", HazardDamageSystem.DEFAULT_DAMAGE))
    try:
        animator = build_hazard_animator({"spin": "assets/graphics/enemies/saw/animation"}, "spin")
    except FileNotFoundError:
        animator = None
    if "size" in obj.properties:
        side = float(obj.properties["size"])
        size = (side, side)
    elif animator is not None:
        size = animator.frame_size
    else:
        size = (World.TILE_SIZE, World.TILE_SIZE)
    surf = pygame.Surface((max(size[0], 1), max(size[1], 1)))
    surf.fill(Colors.black)
    half = pygame.math.Vector2(size[0] / 2, size[1] / 2)
    start, end = _rect_path(obj)
    span_a = (start.x - half.x, start.y - half.y)
    span_b = (end.x - half.x, end.y - half.y)
    hazard = SpanHazard(
        span_a,
        surf,
        speed,
        flip,
        groups.all_sprites,
        damage=damage,
        animator=animator,
        span=(span_a, span_b),
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
    damage = float(obj.properties.get("damage", HazardDamageSystem.DEFAULT_DAMAGE))
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
    damage = float(obj.properties.get("damage", HazardDamageSystem.DEFAULT_DAMAGE))
    try:
        animator = build_hazard_animator(
            {"spikes": "assets/graphics/enemies/floor_spikes"}, "spikes"
        )
    except FileNotFoundError:
        animator = None
    hazard = SpanHazard(
        (obj.x, obj.y), surf, 0.0, False, groups.all_sprites, damage=damage, animator=animator
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

    def __init__(self, level_data: LevelData, gameplay_data: GameplayData | None = None) -> None:
        self.level_data = level_data
        self.gameplay_data = gameplay_data

    def build(self, groups: SpriteGroups, input_manager: InputManager) -> Player:
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

        for object_layer in self.level_data.object_layers.values():
            if object_layer.name == "Data":
                continue
            for obj in object_layer.objects:
                self._build_object(obj, groups, player)

        return player

    def _build_player(self, groups: SpriteGroups, input_manager: InputManager) -> Player | None:
        """Locate the player object and instantiate it."""
        config = self.gameplay_data.player if self.gameplay_data is not None else None
        for layer in self.level_data.object_layers.values():
            for obj in layer.objects:
                if obj.name == "player":
                    player = Player(
                        (obj.x, obj.y),
                        groups.all_sprites,
                        groups.collision_sprites,
                        groups.moving_platforms,
                        input_manager,
                        config=config,
                    )
                    groups.combat_sprites.add(player)
                    groups.entity_sprites.add(player)
                    return player
        return None

    def _build_object(self, obj: ObjectData, groups: SpriteGroups, player: Player | None) -> None:
        """
        Build a single object from an object layer.

        Handles enemies (via factory), registered object types,
        and static images.
        """
        if obj.name == "player":
            return
        if is_enemy_type(obj.name):
            config = (
                self.gameplay_data.enemies.get(obj.name) if self.gameplay_data is not None else None
            )
            entity = create_enemy(
                obj.name,
                pos=(obj.x, obj.y),
                groups=(groups.all_sprites,),
                collision_sprites=groups.collision_sprites,
                player_reference=player,
                config=config,
            )
            groups.combat_sprites.add(entity)
            groups.entity_sprites.add(entity)
        elif OBJECT_FACTORIES.has(obj.name):
            OBJECT_FACTORIES.dispatch(obj.name, obj, groups)
        elif obj.image is not None:
            Sprite(pos=(obj.x, obj.y), surf=obj.image, groups=groups.all_sprites)
        else:
            logger.debug("Object '%s' has no factory or image, ignored", obj.name)
