import pygame

from colors import Colors
from enemy import Goblin
from player import Player
from settings import DEBUG, World
from sprites import MovingPlatform, Sprite


class Level:
    def __init__(self, display_surface, tmx_map):
        self.display_surface = display_surface
        self.all_sprites = pygame.sprite.Group()
        self.collision_sprites = pygame.sprite.Group()
        self.moving_platforms = pygame.sprite.Group()

        self.combat_sprites = pygame.sprite.Group()
        self.entity_sprites = pygame.sprite.Group()

        self.player = None

        self.hit_stop_timer = 0.0
        self.spawn_cooldown = 0.0

        self.setup(tmx_map)

        self.debug_font = pygame.font.SysFont("Arial", 24)
        self.label_font = pygame.font.SysFont("Arial", 16)

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

    def _draw_panel(
        self, x: int, y: int, lines: list, color: tuple, text_color: tuple
    ) -> int:
        """Renders a generic text panel. Returns its height."""
        font = self.debug_font
        padding = 8
        line_height = 28

        rendered = [font.render(line, True, text_color) for line in lines]
        max_w = max(s.get_width() for s in rendered) if rendered else 0
        panel_w = max_w + padding * 2
        panel_h = len(lines) * line_height + padding * 2

        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill(color)
        self.display_surface.blit(bg, (x, y))

        for i, surf in enumerate(rendered):
            self.display_surface.blit(
                surf, (x + padding, y + padding + i * line_height)
            )

        return panel_h

    def _draw_state_panel(self, x: int, y: int) -> int:
        """
        Draws the player state machine panel.
        Exploits StateMachine.history and previous_state_name from the refactored SM.
        Returns panel height.
        """
        if self.player is None or self.player.state_machine is None:
            return 0

        sm = self.player.state_machine
        current = sm.current_state_name or "None"
        previous = sm.previous_state_name or "—"
        history = sm.history[-6:] if sm.history else []

        lines = [
            f"State:  {current}",
            f"Prev:   {previous}",
            f"Hist:   {' → '.join(history)}",
            f"Vel:    ({self.player.velocity.x:.1f}, {self.player.velocity.y:.1f})",
            f"Floor: {self.player.on_surface['floor']}   L: {self.player.on_surface['left']}   R: {self.player.on_surface['right']}",
        ]
        if self.player.combat.is_attacking:
            lines.append(f"Attack: {self.player.combat.current_attack}")

        return self._draw_panel(x, y, lines, (0, 0, 0, 180), Colors.white)

    def _draw_stats_panel(self, x: int, y: int) -> int:
        """Draws player resource panel (HP, block, dash). Returns panel height."""
        if self.player is None:
            return 0

        p = self.player
        lines = [
            f"HP:    {getattr(p, 'health', 100):.0f}",
            f"Block: {p.block_stamina:.2f}/{p.max_block_stamina:.2f}   CD: {p.block_cooldown_timer:.2f}s",
            f"Dash:  {p.dash_charges}/{p.max_dash_charges}   Pen: {p.dash_penalty_timer:.2f}s   Regen: {p.dash_recharge_timer:.2f}s",
        ]
        return self._draw_panel(x, y, lines, (20, 20, 40, 200), Colors.off_white)

    def _draw_performance_panel(self) -> None:
        """Draws a performance panel at the top-right corner."""
        lines = [
            f"FPS:       {self.current_fps:.1f}",
            f"Sprites:   {len(self.all_sprites)}",
            f"Combat:    {len(self.combat_sprites)}",
            f"Entities:  {len(self.entity_sprites)}",
            f"Collision: {len(self.collision_sprites)}",
            f"Hit Stop:  {self.hit_stop_timer:.3f}",
            f"Spawn CD:  {self.spawn_cooldown:.3f}",
        ]
        font = self.debug_font
        padding = 8
        line_height = 28

        rendered = [font.render(line, True, Colors.light_blue) for line in lines]
        max_w = max(s.get_width() for s in rendered)
        panel_w = max_w + padding * 2
        panel_h = len(lines) * line_height + padding * 2
        panel_x = self.display_surface.get_width() - panel_w - 10
        panel_y = 10

        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill((0, 0, 30, 200))
        self.display_surface.blit(bg, (panel_x, panel_y))

        for i, surf in enumerate(rendered):
            self.display_surface.blit(
                surf, (panel_x + padding, panel_y + padding + i * line_height)
            )

    def _draw_debug_overlays(self) -> None:
        """Draws hitboxes, attack boxes, and floating state labels for all entities."""
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
            if not hasattr(sprite, "state_machine") or sprite.state_machine is None:
                continue

            state = sprite.state_machine.current_state_name or "None"
            label_surf = self.label_font.render(
                f"{sprite.__class__.__name__}: {state}", True, (255, 255, 200)
            )
            ref = (
                sprite.hitbox
                if (hasattr(sprite, "hitbox") and sprite.hitbox)
                else sprite.rect
            )
            bg = label_surf.get_rect(midbottom=(ref.centerx, ref.top - 8))
            bg.left = max(0, min(bg.left, self.display_surface.get_width() - bg.width))
            bg.top = max(0, bg.top)

            pygame.draw.rect(self.display_surface, (0, 0, 0, 160), bg, border_radius=4)
            self.display_surface.blit(label_surf, bg)

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
            self._draw_debug_overlays()

            x, y = 10, 10
            y += self._draw_state_panel(x, y) + 8
            self._draw_stats_panel(x, y)

            self._draw_performance_panel()