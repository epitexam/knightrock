import pygame
from src.core.colors import Colors
from src.core.camera import Camera
from src.core.settings import Debug


class UIManager:
    """Draw UI overlays and debug panels."""
    def __init__(self, display_surface: pygame.Surface) -> None:
        """Initialize the UIManager instance."""
        self.display_surface = display_surface
        self.debug_font = pygame.font.SysFont("Arial", Debug.FONT_SIZE)
        self.label_font = pygame.font.SysFont("Arial", Debug.LABEL_FONT_SIZE)

    def draw_panel(
        self, x: int, y: int, lines: list[str], color: tuple, text_color: tuple
    ) -> int:
        """Draw panel."""
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

    def draw_state_panel(self, x: int, y: int, player) -> int:
        """Draw state panel."""
        if player is None or player.state_machine is None:
            return 0

        sm = player.state_machine
        current = sm.current_state_name or "None"
        previous = sm.previous_state_name or "—"
        history = list(sm.history)[-6:] if sm.history else []

        lines = [
            f"State:  {current}",
            f"Prev:   {previous}",
            f"Hist:   {' → '.join(history)}",
            f"Vel:    ({player.velocity.x:.1f}, {player.velocity.y:.1f})",
            f"Floor: {player.on_surface['floor']}   L: {player.on_surface['left']}   R: {player.on_surface['right']}",
            f"Axis:   {player.move_axis:+.2f}",
            f"Jump:   buf {player.jump_buffer_timer:.2f}s  coy {player.coyote_timer:.2f}s",
            f"Jumps:  mid {player.midair_jumps_left}  wall {player.wall_jumps_left}",
            f"Dash:   req {player._dash_requested}  dur {player._dash_duration_timer:.2f}s",
        ]

        combat = player.combat
        if combat is not None:
            attack_name = combat.current_attack or "—"
            if combat.current_attack and combat.current_phase is not None:
                phase_text = f"{combat.current_phase_index}/{len(combat.attacks[combat.current_attack].phases) - 1}"
            else:
                phase_text = "idle"
            lines.append(f"Combat: {attack_name}  phase {phase_text}")
            lines.append(
                f"Hurt:   {combat.is_hurt}  timer {combat.hurt_timer:.2f}s  dmg {combat.contact_damage}"
            )
            if combat.is_charging and combat.charging_attack_name:
                lines.append(
                    f"Charge: {combat.charging_attack_name} {combat.charge_timer:.2f}s"
                )
            cooldowns = [
                f"{name}:{cd:.2f}s"
                for name, cd in combat.cooldowns.items()
                if cd > 0
            ]
            if cooldowns:
                lines.append("CDs:    " + ", ".join(cooldowns[:4]))

        if hasattr(player, "stagger_timer") and player.stagger_timer > 0:
            lines.append(f"Stagger: {player.stagger_timer:.2f}s")
        if hasattr(player, "invincibility_timer") and player.invincibility_timer > 0:
            lines.append(f"Invincible: {player.invincibility_timer:.2f}s")

        return self.draw_panel(x, y, lines, (0, 0, 0, 180), Colors.white)

    def draw_stats_panel(self, x: int, y: int, player) -> int:
        """Draw stats panel."""
        if player is None:
            return 0

        p = player
        lines = [
            f"HP:    {p.health:.0f}/{p.max_health:.0f}",
            f"Block: {p.block_stamina:.2f}/{p.max_block_stamina:.2f}   CD: {p.block_cooldown_timer:.2f}s",
            f"Dash:  {p.dash_charges}/{p.max_dash_charges}   Pen: {p.dash_penalty_timer:.2f}s   Regen: {p.dash_recharge_timer:.2f}s",
            f"Move:  spd {p.speed:.0f}  ctrl {p.floor_control:.1f}/{p.air_control:.1f}",
            f"Jump:  h {p.jump_height:.0f}  wall {p.wall_jump_height:.0f}",
            f"Dash:  spd {p.dash_speed:.0f}  duration {p.dash_duration:.2f}s  fric {p.dash_friction:.1f}",
        ]

        combo_count = p.combat.combo_count if hasattr(
            p.combat, "combo_count") else 0
        combo_timer = p.combat.combo_timer if hasattr(
            p.combat, "combo_timer") else 0.0
        lines.append(f"Combo: {combo_count}   Timer: {combo_timer:.2f}s")

        return self.draw_panel(x, y, lines, (20, 20, 40, 200), Colors.off_white)

    def draw_performance_panel(
        self,
        fps: float,
        sprite_count: int,
        combat_count: int,
        entity_count: int,
        collision_count: int,
        hit_stop: float,
        spawn_cd: float,
    ) -> None:
        """Draw performance panel."""
        lines = [
            f"FPS:       {fps:.1f}",
            f"Sprites:   {sprite_count}",
            f"Combat:    {combat_count}",
            f"Entities:  {entity_count}",
            f"Collision: {collision_count}",
            f"Hit Stop:  {hit_stop:.3f}",
            f"Spawn CD:  {spawn_cd:.3f}",
        ]

        font = self.debug_font
        padding = 8
        line_height = 28

        max_w = max(font.size(line)[0] for line in lines)
        panel_w = max_w + padding * 2
        panel_h = len(lines) * line_height + padding * 2
        panel_x = self.display_surface.get_width() - panel_w - 10
        panel_y = 10

        self.draw_panel(panel_x, panel_y, lines,
                        (0, 0, 30, 200), Colors.light_blue)

    def draw_debug_overlays(
        self, all_sprites: pygame.sprite.Group, camera: Camera
    ) -> None:
        """Draw debug overlays."""
        for sprite in all_sprites:
            if hasattr(sprite, "hitbox") and sprite.hitbox:
                rect = camera.apply(sprite.hitbox)
                pygame.draw.rect(self.display_surface,
                                 (0, 0, 255), rect, width=2)
            if hasattr(sprite, "combat") and sprite.combat.attack_box:
                rect = camera.apply(sprite.combat.attack_box)
                pygame.draw.rect(
                    self.display_surface,
                    (255, 165, 0),
                    rect,
                    width=3,
                )

        for sprite in all_sprites:
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
            ref = camera.apply(ref)
            bg = label_surf.get_rect(midbottom=(ref.centerx, ref.top - 8))
            bg.left = max(
                0, min(bg.left, self.display_surface.get_width() - bg.width))
            bg.top = max(0, bg.top)

            pygame.draw.rect(self.display_surface,
                             (0, 0, 0, 160), bg, border_radius=4)
            self.display_surface.blit(label_surf, bg)

    def draw_health_bars(
        self, entities: pygame.sprite.Group | list, camera: Camera
    ) -> None:
        """
            Draws a health bar above each entity with `health` / `max_health`.
            The bar is centered and dynamically adjusts to avoid overlapping the debug text.
        """
        for entity in entities:
            if not hasattr(entity, "health") or not hasattr(entity, "max_health"):
                continue

            if getattr(entity, "is_dead", False):
                continue

            rect = entity.hitbox if hasattr(
                entity, "hitbox") and entity.hitbox else entity.rect
            if rect is None:
                continue

            screen_rect = camera.apply(rect)

            bar_width = max(30, min(screen_rect.width * 0.8, 60))
            bar_height = 6

            bar_x = screen_rect.centerx - (bar_width / 2)

            base_offset = 8

            if Debug.ENABLED:
                base_offset += self.label_font.get_height() + 4

            bar_y = screen_rect.top - base_offset - bar_height

            border_rect = (bar_x - 1, bar_y - 1, bar_width + 2, bar_height + 2)
            bg_rect = (bar_x, bar_y, bar_width, bar_height)

            pygame.draw.rect(self.display_surface, (0, 0, 0), border_rect, 1)
            pygame.draw.rect(self.display_surface, (40, 40, 40), bg_rect)

            health_ratio = max(
                0.0, min(1.0, entity.health / entity.max_health))
            health_width = bar_width * health_ratio

            if health_ratio > 0.5:
                color = (46, 204, 113)
            elif health_ratio > 0.25:
                color = (241, 196, 15)
            else:
                color = (231, 76, 60)

            if health_width > 0:
                pygame.draw.rect(
                    self.display_surface,
                    color,
                    (bar_x, bar_y, health_width, bar_height)
                )
