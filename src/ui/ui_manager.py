import pygame
from src.core.colors import Colors
from src.core.camera import Camera
from src.core.settings import Debug

PANEL_BG = (20, 22, 26, 220)
PANEL_BORDER = (90, 100, 110)
TEXT_MUTED = (185, 192, 198)
TEXT_TITLE = (215, 220, 224)
TEXT_WARN = (200, 150, 90)
TEXT_CRIT = (190, 100, 100)
TEXT_OK = (120, 170, 140)


class UIManager:
    """Draw UI overlays and debug panels."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        """Initialize the UIManager instance."""
        self.display_surface = display_surface
        self.debug_font = pygame.font.SysFont("Consolas", Debug.FONT_SIZE)
        self.title_font = pygame.font.SysFont(
            "Consolas", Debug.FONT_SIZE, bold=True)
        self.label_font = pygame.font.SysFont(
            "Consolas", Debug.LABEL_FONT_SIZE)

    def draw_panel(
        self,
        x: int,
        y: int,
        lines: list[str],
        color: tuple = PANEL_BG,
        text_color: tuple = TEXT_MUTED,
        title: str | None = None,
        line_colors: dict[int, tuple] | None = None,
    ) -> int:
        font = self.debug_font
        padding = 12
        line_height = 23
        title_gap = 8
        line_colors = line_colors or {}

        rendered = [font.render(line, True, line_colors.get(i, text_color))
                    for i, line in enumerate(lines)]
        max_w = max(s.get_width() for s in rendered) if rendered else 0

        title_surf = None
        title_block_h = 0
        if title:
            title_surf = self.title_font.render(title, True, TEXT_TITLE)
            max_w = max(max_w, title_surf.get_width())
            title_block_h = title_surf.get_height() + title_gap + 1 + title_gap

        panel_w = max_w + padding * 2
        panel_h = title_block_h + len(lines) * line_height + padding * 2

        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(bg, color, (0, 0, panel_w, panel_h))
        pygame.draw.rect(bg, PANEL_BORDER, (0, 0, panel_w, panel_h), width=1)
        self.display_surface.blit(bg, (x, y))

        content_y = y + padding
        if title_surf:
            self.display_surface.blit(title_surf, (x + padding, content_y))
            content_y += title_surf.get_height() + title_gap
            pygame.draw.line(
                self.display_surface, PANEL_BORDER,
                (x + padding, content_y), (x + panel_w - padding, content_y), 1,
            )
            content_y += title_gap + 1

        for i, surf in enumerate(rendered):
            self.display_surface.blit(
                surf, (x + padding, content_y + i * line_height))

        return panel_h + 12

    def draw_state_panel(self, x: int, y: int, player) -> int:
        """Draw state panel."""
        if player is None or player.state_machine is None:
            return 0

        sm = player.state_machine
        current = sm.current_state_name or "None"
        previous = sm.previous_state_name or "-"
        history = list(sm.history)[-6:] if sm.history else []

        lines = [
            f"State  {current}   (prev {previous})",
            f"Hist   {' > '.join(history)}",
            f"Vel    ({player.velocity.x:6.1f}, {player.velocity.y:6.1f})",
            f"Floor {player.on_surface['floor']!s:5}  L {player.on_surface['left']!s:5}  R {player.on_surface['right']!s:5}",
            f"Axis   {player.move_axis:+.2f}",
            f"Jump   buf {player.jump_buffer_timer:.2f}s  coy {player.coyote_timer:.2f}s",
            f"Jumps  mid {player.midair_jumps_left}  wall {player.wall_jumps_left}",
            f"Dash   req {player._dash_requested!s:5}  dur {player._dash_duration_timer:.2f}s",
        ]
        line_colors = {}

        combat = player.combat
        if combat is not None:
            attack_name = combat.current_attack or "-"
            if combat.current_attack and combat.current_phase is not None:
                phase_text = f"{combat.current_phase_index}/{len(combat.attacks[combat.current_attack].phases) - 1}"
            else:
                phase_text = "idle"
            lines.append(f"Combat {attack_name}  phase {phase_text}")

            hurt_idx = len(lines)
            lines.append(
                f"Hurt   {combat.is_hurt!s:5} {combat.hurt_timer:.2f}s")
            if combat.is_hurt:
                line_colors[hurt_idx] = TEXT_CRIT

            if combat.is_charging and combat.charging_attack_name:
                idx = len(lines)
                lines.append(
                    f"Charge {combat.charging_attack_name} {combat.charge_timer:.2f}s")
                line_colors[idx] = TEXT_WARN

            cooldowns = [
                f"{name}:{cd:.2f}s" for name, cd in combat.cooldowns.items() if cd > 0
            ]
            if cooldowns:
                lines.append("CDs    " + ", ".join(cooldowns[:4]))

        if hasattr(player, "stagger_timer") and player.stagger_timer > 0:
            idx = len(lines)
            lines.append(f"Stagger {player.stagger_timer:.2f}s")
            line_colors[idx] = TEXT_WARN

        if hasattr(player, "invincibility_timer") and player.invincibility_timer > 0:
            idx = len(lines)
            lines.append(f"Invincible {player.invincibility_timer:.2f}s")
            line_colors[idx] = TEXT_OK

        return self.draw_panel(x, y, lines, title="PLAYER STATE", line_colors=line_colors)

    def draw_stats_panel(self, x: int, y: int, player) -> int:
        if player is None:
            return 0

        p = player
        hp_ratio = p.health / p.max_health if p.max_health else 0
        hp_color = TEXT_OK if hp_ratio > 0.5 else TEXT_WARN if hp_ratio > 0.25 else TEXT_CRIT

        lines = [
            f"HP     {p.health:.0f}/{p.max_health:.0f}",
            f"Block  {p.block_stamina:.2f}/{p.max_block_stamina:.2f}   cd {p.block_cooldown_timer:.2f}s",
            f"Dash   {p.dash_charges}/{p.max_dash_charges}   pen {p.dash_penalty_timer:.2f}s  regen {p.dash_recharge_timer:.2f}s",
            f"Move   spd {p.speed:.0f}  ctrl {p.floor_control:.1f}/{p.air_control:.1f}",
            f"Jump   h {p.jump_height:.0f}  wall {p.wall_jump_height:.0f}",
            f"Dash   spd {p.dash_speed:.0f}  dur {p.dash_duration:.2f}s  fric {p.dash_friction:.1f}",
        ]

        combo_count = p.combat.combo_count if hasattr(
            p.combat, "combo_count") else 0
        combo_timer = p.combat.combo_timer if hasattr(
            p.combat, "combo_timer") else 0.0
        lines.append(f"Combo  x{combo_count}   {combo_timer:.2f}s")

        return self.draw_panel(x, y, lines, title="STATS", line_colors={0: hp_color})

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
        fps_color = TEXT_OK if fps >= 55 else TEXT_WARN if fps >= 30 else TEXT_CRIT

        lines = [
            f"FPS        {fps:5.1f}",
            f"Sprites    {sprite_count}",
            f"Combat     {combat_count}",
            f"Entities   {entity_count}",
            f"Collision  {collision_count}",
            f"Hit Stop   {hit_stop:.3f}",
            f"Spawn CD   {spawn_cd:.3f}",
        ]

        font = self.debug_font
        padding = 12
        line_height = 23
        title_block_h = self.title_font.get_height() + 8 + 1 + 8

        max_w = max(font.size(line)[0] for line in lines)
        panel_w = max_w + padding * 2
        panel_h = title_block_h + len(lines) * line_height + padding * 2
        panel_x = self.display_surface.get_width() - panel_w - 12
        panel_y = 12

        self.draw_panel(
            panel_x, panel_y, lines, title="PERFORMANCE", line_colors={0: fps_color}
        )

    def draw_debug_overlays(
        self, all_sprites: pygame.sprite.Group, camera: Camera
    ) -> None:
        """Draw debug overlays."""
        for sprite in all_sprites:
            if hasattr(sprite, "hitbox") and sprite.hitbox:
                rect = camera.apply(sprite.hitbox)
                pygame.draw.rect(self.display_surface,
                                 (100, 140, 160), rect, width=1)
            if hasattr(sprite, "combat") and sprite.combat.attack_box:
                rect = camera.apply(sprite.combat.attack_box)
                pygame.draw.rect(self.display_surface,
                                 (170, 120, 80), rect, width=2)

        for sprite in all_sprites:
            if not hasattr(sprite, "state_machine") or sprite.state_machine is None:
                continue

            state = sprite.state_machine.current_state_name or "None"
            label_surf = self.label_font.render(
                f"{sprite.__class__.__name__}: {state}", True, TEXT_MUTED
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
            bg.inflate_ip(12, 6)

            panel = pygame.Surface(bg.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (18, 20, 24, 210), (0, 0, *bg.size))
            pygame.draw.rect(panel, PANEL_BORDER, (0, 0, *bg.size), width=1)
            self.display_surface.blit(panel, bg.topleft)
            self.display_surface.blit(
                label_surf, label_surf.get_rect(center=bg.center))

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

            bg_rect = (bar_x, bar_y, bar_width, bar_height)
            pygame.draw.rect(self.display_surface, (35, 37, 40), bg_rect)

            health_ratio = max(
                0.0, min(1.0, entity.health / entity.max_health))
            health_width = bar_width * health_ratio

            color = TEXT_OK if health_ratio > 0.5 else TEXT_WARN if health_ratio > 0.25 else TEXT_CRIT

            if health_width > 0:
                pygame.draw.rect(
                    self.display_surface, color, (bar_x,
                                                  bar_y, health_width, bar_height)
                )

            pygame.draw.rect(self.display_surface,
                             PANEL_BORDER, bg_rect, width=1)
