import pygame
from src.core.colors import Colors
from src.core.settings import World
from src.core.sprites import MovingPlatform, Sprite
from src.entities.player import Player
from src.entities.enemy import Goblin


class WorldBuilder:
    ENTITY_CLASSES = {
        "player": Player,
        "goblin": Goblin,
    }

    def __init__(self, tmx_map):
        self.tmx_map = tmx_map

    def build(self, all_sprites, collision_sprites, moving_platforms,
              combat_sprites, entity_sprites, input_manager):
        self._setup_terrain(all_sprites, collision_sprites)
        self._setup_platforms(all_sprites, collision_sprites, moving_platforms)
        player = self._setup_entities(
            all_sprites, collision_sprites, moving_platforms,
            combat_sprites, entity_sprites, input_manager
        )
        return player

    def _setup_terrain(self, all_sprites, collision_sprites):
        for x, y, surf in self.tmx_map.get_layer_by_name("Terrain").tiles():
            Sprite(
                pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
                color=Colors.blue,
                surf=surf,
                groups=(all_sprites, collision_sprites),
            )

    def _setup_platforms(self, all_sprites, collision_sprites, moving_platforms):
        for obj in self.tmx_map.get_layer_by_name("Moving Objects"):
            if obj.name == "helicopter":
                waypoints_str = obj.properties.get("waypoints", "")
                if waypoints_str:
                    points = []
                    for point in waypoints_str.split(";"):
                        x_str, y_str = point.split(",")
                        points.append((int(x_str), int(y_str)))
                else:
                    end_x = obj.properties.get("end_x", obj.x + 100)
                    end_y = obj.properties.get("end_y", obj.y)
                    points = [(obj.x, obj.y), (end_x, end_y)]

                speed = obj.properties.get("speed", 100)

                min_thickness = World.TILE_SIZE // 2
                if obj.height < min_thickness:
                    width = max(obj.width, min_thickness)
                    height = min_thickness
                elif obj.width < min_thickness:
                    width = min_thickness
                    height = max(obj.height, min_thickness)
                else:
                    width, height = obj.width, obj.height

                surf = pygame.Surface((width, height))
                surf.fill(Colors.gold)

                platform = MovingPlatform(
                    (obj.x, obj.y),
                    surf,
                    points,
                    speed,
                    (all_sprites, collision_sprites),
                )
                moving_platforms.add(platform)

    def _setup_entities(self, all_sprites, collision_sprites, moving_platforms,
                        combat_sprites, entity_sprites, input_manager):
        player = None
        for obj in self.tmx_map.get_layer_by_name("Objects"):
            cls = self.ENTITY_CLASSES.get(obj.name)
            if cls is None:
                continue
            if obj.name == "player":
                player = Player(
                    (obj.x, obj.y),
                    all_sprites,
                    collision_sprites,
                    moving_platforms,
                    input_manager,
                )
                combat_sprites.add(player)
                entity_sprites.add(player)
            else:
                entity = cls(
                    pos=(obj.x, obj.y),
                    groups=(all_sprites,),
                    collision_sprites=collision_sprites,
                    player_reference=player,
                )
                combat_sprites.add(entity)
                entity_sprites.add(entity)
        return player