import pygame

from colors import Colors
from player import Player
from settings import World
from sprites import MovingPlatform, Sprite


class Level:
    def __init__(self, display_surface, tmx_map):
        self.display_surface = display_surface
        self.all_sprites = pygame.sprite.Group()
        self.collision_sprites = pygame.sprite.Group()
        self.moving_platforms = pygame.sprite.Group()
        self.player = None
        self.setup(tmx_map)
        self.debug_font = pygame.font.SysFont("Arial", 24)

    def setup(self, tmx_map):
        for x, y, surf in tmx_map.get_layer_by_name("Terrain").tiles():
            Sprite(
                pos=(x * World.TILE_SIZE, y * World.TILE_SIZE),
                color=Colors.blue,
                surf=surf,
                groups=(self.all_sprites, self.collision_sprites),
            )

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

        for obj in tmx_map.get_layer_by_name("Objects"):
            if obj.name == "player":
                self.player = Player(
                    (obj.x, obj.y),
                    self.all_sprites,
                    self.collision_sprites,
                    self.moving_platforms,
                )

    def run(self, delta_time):
        self.all_sprites.update(delta_time)
        self.display_surface.fill(Colors.red)
        self.all_sprites.draw(self.display_surface)

        for sprite in self.all_sprites:
            if hasattr(sprite, "hitbox") and sprite.hitbox:
                pygame.draw.rect(
                    self.display_surface, (0, 0, 255), sprite.hitbox, width=2
                )

            if hasattr(sprite, "combat") and sprite.combat.attack_box:
                pygame.draw.rect(
                    self.display_surface,
                    (255, 165, 0),
                    sprite.combat.attack_box,
                    width=3,
                )

        if self.player is not None and self.player.state_machine is not None:
            state_name = self.player.state_machine.current_state_name or "None"
            debug_text = f"Player state: {state_name}"
            text_surf = self.debug_font.render(debug_text, True, (255, 255, 255))
            self.display_surface.blit(text_surf, (10, 10))

            vel_text = (
                f"Vel: ({self.player.velocity.x:.1f}, {self.player.velocity.y:.1f})"
            )
            vel_surf = self.debug_font.render(vel_text, True, (200, 200, 200))
            self.display_surface.blit(vel_surf, (10, 40))

            surf_text = (
                f"Floor: {self.player.on_surface['floor']}  "
                f"Left: {self.player.on_surface['left']}  "
                f"Right: {self.player.on_surface['right']}"
            )
            surf_surf = self.debug_font.render(surf_text, True, (200, 200, 200))
            self.display_surface.blit(surf_surf, (10, 70))

            if self.player.combat.is_attacking:
                atk_text = f"Attacking: {self.player.combat.current_attack}"
                atk_surf = self.debug_font.render(atk_text, True, (255, 200, 100))
                self.display_surface.blit(atk_surf, (10, 100))
