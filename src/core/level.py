import pygame

from src.core.colors import Colors
from src.entities.enemy import Goblin
from src.entities.player import Player
from src.core.settings import DEBUG, World
from src.core.sprites import MovingPlatform, Sprite
from src.ui.ui_manager import UIManager
from src.core.input_manager import InputManager


class Level:
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

        self.hit_stop_timer = 0.0
        self.spawn_cooldown = 0.0

        self.setup(tmx_map)

        self.fps_timer = 0.0
        self.fps_frames = 0
        self.current_fps = 0

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
                    self.input_manager,
                )
                self.combat_sprites.add(self.player)
                self.entity_sprites.add(self.player)

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

    def _handle_combat(self):
        for attacker in self.combat_sprites:
            if not attacker.combat.is_attacking or not attacker.combat.attack_box:
                continue
            phase = attacker.combat.current_phase
            if phase is None:
                continue

            for target in self.combat_sprites:
                if attacker is target:
                    continue
                if target in attacker.combat.targets_hit:
                    continue

                if attacker.combat.attack_box.colliderect(target.hurtbox):
                    target.combat.take_damage(
                        amount=phase.damage,
                        source_center_x=attacker.hitbox.centerx,
                        knockback=phase.knockback,
                    )
                    attacker.combat.targets_hit.add(target)
                    self.hit_stop_timer = 0.05 + (phase.damage * 0.002)

    def _handle_entity_interactions(self, delta_time: float):
        entities = list(self.entity_sprites)

        for i, ent_a in enumerate(entities):
            for ent_b in entities[i + 1 :]:
                if type(ent_a) is type(ent_b):
                    continue

                if not ent_a.hitbox.colliderect(ent_b.hitbox):
                    continue

                if not ent_a.combat.is_hurt and ent_b.combat.contact_damage > 0:
                    ent_a.combat.take_damage(
                        ent_b.combat.contact_damage,
                        source_center_x=ent_b.hitbox.centerx,
                    )
                elif not ent_b.combat.is_hurt and ent_a.combat.contact_damage > 0:
                    ent_b.combat.take_damage(
                        ent_a.combat.contact_damage,
                        source_center_x=ent_a.hitbox.centerx,
                    )

                overlap_x = min(ent_a.hitbox.right, ent_b.hitbox.right) - max(
                    ent_a.hitbox.left, ent_b.hitbox.left
                )
                overlap_y = min(ent_a.hitbox.bottom, ent_b.hitbox.bottom) - max(
                    ent_a.hitbox.top, ent_b.hitbox.top
                )

                if overlap_x <= 0 or overlap_y <= 0:
                    continue

                if overlap_x <= overlap_y:
                    dir_a = -1.0 if ent_a.hitbox.centerx < ent_b.hitbox.centerx else 1.0
                    dir_b = -dir_a
                    if ent_a.pushable and ent_b.pushable:
                        ent_a.hitbox.x += (overlap_x / 2.0) * dir_a
                        ent_b.hitbox.x += (overlap_x / 2.0) * dir_b
                    elif ent_a.pushable:
                        ent_a.hitbox.x += overlap_x * dir_a
                    elif ent_b.pushable:
                        ent_b.hitbox.x += overlap_x * dir_b
                else:
                    dir_a = -1.0 if ent_a.hitbox.centery < ent_b.hitbox.centery else 1.0
                    dir_b = -dir_a
                    if ent_a.pushable and ent_b.pushable:
                        ent_a.hitbox.y += (overlap_y / 2.0) * dir_a
                        ent_b.hitbox.y += (overlap_y / 2.0) * dir_b
                    elif ent_a.pushable:
                        ent_a.hitbox.y += overlap_y * dir_a
                    elif ent_b.pushable:
                        ent_b.hitbox.y += overlap_y * dir_b

                ent_a.sync_rects()
                ent_b.sync_rects()

    def run(self, delta_time: float):
        self.fps_frames += 1
        self.fps_timer += delta_time
        if self.fps_timer >= 1.0:
            self.current_fps = self.fps_frames / self.fps_timer
            self.fps_frames = 0
            self.fps_timer = 0.0

        self._handle_debug_input(delta_time)

        if self.hit_stop_timer > 0:
            self.hit_stop_timer -= delta_time
        else:
            self.all_sprites.update(delta_time)
            self._handle_entity_interactions(delta_time)
            self._handle_combat()

        self.display_surface.fill(Colors.red)
        self.all_sprites.draw(self.display_surface)

        if DEBUG:
            self.ui_manager.draw_debug_overlays(self.all_sprites)

            x, y = 10, 10
            y += self.ui_manager.draw_state_panel(x, y, self.player) + 8
            self.ui_manager.draw_stats_panel(x, y, self.player)

            self.ui_manager.draw_performance_panel(
                fps=self.current_fps,
                sprite_count=len(self.all_sprites),
                combat_count=len(self.combat_sprites),
                entity_count=len(self.entity_sprites),
                collision_count=len(self.collision_sprites),
                hit_stop=self.hit_stop_timer,
                spawn_cd=self.spawn_cooldown,
            )
