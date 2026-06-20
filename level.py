import pygame

from colors import Colors
from enemy import Goblin
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

        self.hit_stop_timer = 0.0
        self.spawn_cooldown = 0.0

        self.setup(tmx_map)

        self.debug_font = pygame.font.SysFont("Arial", 24)
        self.label_font = pygame.font.SysFont("Arial", 16)

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

    def _handle_debug_input(self, delta_time: float):
        """Listens for keyboard inputs dedicated to level debugging."""
        if self.spawn_cooldown > 0:
            self.spawn_cooldown -= delta_time

        keys = pygame.key.get_pressed()

        if keys[pygame.K_g] and self.spawn_cooldown <= 0 and self.player is not None:
            offset_x = 100 if self.player.facing_right else -100
            spawn_x = self.player.hitbox.centerx + offset_x
            spawn_y = self.player.hitbox.top

            Goblin(
                pos=(spawn_x, spawn_y),
                groups=(self.all_sprites,),
                collision_sprites=self.collision_sprites,
                player_reference=self.player,
            )

            self.spawn_cooldown = 0.5

    def _handle_combat(self):
        """Detects collisions between attack_box (weapons) and hitbox (body)."""
        combatants = [s for s in self.all_sprites if hasattr(s, "combat")]

        for attacker in combatants:
            if not attacker.combat.is_attacking or not attacker.combat.attack_box:
                continue

            for target in combatants:
                if attacker == target:
                    continue

                if target in attacker.combat.targets_hit:
                    continue

                if target.combat.is_hurt:
                    continue

                if attacker.combat.attack_box.colliderect(target.hitbox):
                    attack_data = attacker.combat.attacks[
                        attacker.combat.current_attack
                    ]

                    target.combat.take_damage(
                        amount=attack_data.damage,
                        source_center_x=attacker.hitbox.centerx,
                    )

                    attacker.combat.targets_hit.add(target)

                    self.hit_stop_timer = 0.05 + (attack_data.damage * 0.002)

    def run(self, delta_time):

        self._handle_debug_input(delta_time)

        if self.hit_stop_timer > 0:
            self.hit_stop_timer -= delta_time
        else:
            self.all_sprites.update(delta_time)
            self._handle_combat()

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

        for sprite in self.all_sprites:
            if hasattr(sprite, "state_machine") and sprite.state_machine is not None:
                state = sprite.state_machine.current_state_name or "None"
                entity_name = sprite.__class__.__name__
                label = f"{entity_name}: {state}"
                label_surf = self.label_font.render(label, True, (255, 255, 200))

                if hasattr(sprite, "hitbox") and sprite.hitbox:
                    center_x = sprite.hitbox.centerx
                    top_y = sprite.hitbox.top
                else:
                    center_x = sprite.rect.centerx
                    top_y = sprite.rect.top

                bg_rect = label_surf.get_rect()
                bg_rect.midbottom = (center_x, top_y - 8)

                bg_rect.left = max(
                    0,
                    min(bg_rect.left, self.display_surface.get_width() - bg_rect.width),
                )
                bg_rect.top = max(0, bg_rect.top)

                pygame.draw.rect(
                    self.display_surface, (0, 0, 0, 160), bg_rect, border_radius=4
                )
                self.display_surface.blit(label_surf, bg_rect)

        if self.player is not None and self.player.state_machine is not None:
            panel_x, panel_y = 10, 10
            line_height = 28
            padding = 8
            font = self.debug_font

            lines = [
                f"Player: {self.player.state_machine.current_state_name or 'None'}",
                f"Vel: ({self.player.velocity.x:.1f}, {self.player.velocity.y:.1f})",
                f"Floor: {self.player.on_surface['floor']}  Left: {self.player.on_surface['left']}  Right: {self.player.on_surface['right']}",
            ]
            if self.player.combat.is_attacking:
                lines.append(f"Attack: {self.player.combat.current_attack}")

            max_width = 0
            rendered = []
            for line in lines:
                surf = font.render(line, True, (255, 255, 255))
                rendered.append(surf)
                max_width = max(max_width, surf.get_width())

            panel_width = max_width + padding * 2
            panel_height = len(lines) * line_height + padding * 2

            s = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
            s.fill((0, 0, 0, 180))
            self.display_surface.blit(s, (panel_x, panel_y))

            for i, surf in enumerate(rendered):
                self.display_surface.blit(
                    surf, (panel_x + padding, panel_y + padding + i * line_height)
                )
