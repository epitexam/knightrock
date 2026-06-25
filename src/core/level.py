import pygame
from pytmx.util_pygame import load_pygame

from src.core.colors import Colors
from src.entities.enemy import Goblin
from src.entities.player import Player
from src.core.settings import Debug, World, Display
from src.core.sprites import MovingPlatform, Sprite
from src.ui.ui_manager import UIManager
from src.core.input_manager import InputManager
from src.core.camera import Camera
from src.combat.combat_system import CombatSystem
from src.core.separation_system import SeparationSystem


class Level:
    ENTITY_CLASSES = {
        "player": Player,
        "goblin": Goblin,
    }

    def __init__(self, display_surface, tmx_map, input_manager: InputManager):
        self.display_surface = display_surface
        self.input_manager = input_manager
        self.ui_manager = UIManager(display_surface)

        self.all_sprites = pygame.sprite.Group()
        self.collision_sprites = pygame.sprite.Group()
        self.moving_platforms = pygame.sprite.Group()

        self.combat_sprites = pygame.sprite.Group()
        self.entity_sprites = pygame.sprite.Group()

        self.player = None
        self.spawn_cooldown = 0.0
        self.respawn_timer = 0.0

        self.camera = Camera(Display.WIDTH, Display.HEIGHT)
        self.combat_system = CombatSystem()
        self.separation_system = SeparationSystem()

        self.setup(tmx_map)

    def setup(self, tmx_map):
        self._setup_terrain(tmx_map)
        self._setup_platforms(tmx_map)
        self._setup_entities(tmx_map)

    def _setup_terrain(self, tmx_map):
        for x, y, surf in tmx_map.get_layer_by_name("Terrain").tiles():
            Sprite(
                pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
                color=Colors.blue,
                surf=surf,
                groups=(self.all_sprites, self.collision_sprites),
            )

    def _setup_platforms(self, tmx_map):
        for obj in tmx_map.get_layer_by_name("Moving Objects"):
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
                    (self.all_sprites, self.collision_sprites),
                )
                self.moving_platforms.add(platform)

    def _setup_entities(self, tmx_map):
        for obj in tmx_map.get_layer_by_name("Objects"):
            cls = self.ENTITY_CLASSES.get(obj.name)
            if cls is None:
                continue

            if obj.name == "player":

                self.player = Player(
                    (obj.x, obj.y),
                    self.all_sprites,
                    self.collision_sprites,
                    self.moving_platforms,
                    self.input_manager,
                )
                self.combat_sprites.add(self.player)
                self.entity_sprites.add(self.player)
            else:
                entity = cls(
                    pos=(obj.x, obj.y),
                    groups=(self.all_sprites,),
                    collision_sprites=self.collision_sprites,
                    player_reference=self.player,
                )
                self.combat_sprites.add(entity)
                self.entity_sprites.add(entity)

    def _handle_debug_input(self, delta_time: float):
        if self.spawn_cooldown > 0:
            self.spawn_cooldown -= delta_time

        keys = pygame.key.get_pressed()
        if keys[pygame.K_g] and self.spawn_cooldown <= 0 and self.player is not None:
            offset_x = 100 if self.player.facing_right else -100
            goblin = Goblin(
                pos=(self.player.hitbox.centerx + offset_x, self.player.hitbox.top),
                groups=(self.all_sprites,),
                collision_sprites=self.collision_sprites,
                player_reference=self.player,
            )
            self.combat_sprites.add(goblin)
            self.entity_sprites.add(goblin)
            self.spawn_cooldown = 0.5

    def _remove_dead_entities(self):
        """Remove dead entities except the player (respawn handled separately)."""
        dead = [e for e in self.entity_sprites if e.is_dead and e is not self.player]
        for e in dead:
            e.kill()

    def _draw(self):
        self.display_surface.fill(Colors.red)
        for sprite in self.all_sprites:
            rect = self.camera.apply(sprite.rect)
            self.display_surface.blit(sprite.image, rect)

        if Debug.ENABLED:
            self.ui_manager.draw_debug_overlays(self.all_sprites, self.camera)

    def run(self, delta_time: float, fps: float):
        self._handle_debug_input(delta_time)

        self.combat_system.update_timer(delta_time)

        if not self.combat_system.in_hit_stop:
            self.all_sprites.update(delta_time)
            self.separation_system.process(self.entity_sprites)
            self.combat_system.process_attacks(self.combat_sprites)

        self._remove_dead_entities()

        if self.player is not None and self.player.is_dead:
            self.respawn_timer += delta_time
            if self.respawn_timer >= 2.0:
                self.player.respawn()
                self.respawn_timer = 0.0
        else:
            self.respawn_timer = 0.0

        if self.player is not None and not self.player.is_dead:
            self.camera.follow(self.player.hitbox)

        self._draw()

        if Debug.ENABLED:
            x, y = 10, 10
            y += self.ui_manager.draw_state_panel(x, y, self.player) + 8
            self.ui_manager.draw_stats_panel(x, y, self.player)

            self.ui_manager.draw_performance_panel(
                fps=fps,
                sprite_count=len(self.all_sprites),
                combat_count=len(self.combat_sprites),
                entity_count=len(self.entity_sprites),
                collision_count=len(self.collision_sprites),
                hit_stop=self.combat_system.hit_stop_timer,
                spawn_cd=self.spawn_cooldown,
            )
