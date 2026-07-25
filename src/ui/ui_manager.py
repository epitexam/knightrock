import pygame
from typing import Any, Optional
from src.core.rendering.camera import Camera
from src.core.settings import Debug

# --- UI Constants ---
PANEL_BG = (20, 22, 26, 220)
PANEL_BORDER = (90, 100, 110)
TEXT_MUTED = (185, 192, 198)
TEXT_TITLE = (215, 220, 224)
TEXT_WARN = (200, 150, 90)
TEXT_CRIT = (190, 100, 100)
TEXT_OK = (120, 170, 140)


class UIManager:
    """Draw UI overlays and debug panels, optimized with text caching."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        self.display_surface = display_surface

        # Fonts
        self.debug_font = pygame.font.SysFont("Consolas", Debug.FONT_SIZE)
        self.title_font = pygame.font.SysFont(
            "Consolas", Debug.FONT_SIZE, bold=True)
        self.label_font = pygame.font.SysFont(
            "Consolas", Debug.LABEL_FONT_SIZE)

        # Performance: Cache for rendered text surfaces
        # Key: (text, font_id, color), Value: pygame.Surface
        self._text_cache: dict[tuple, pygame.Surface] = {}

    def _render_text(self, text: str, font: pygame.font.Font, color: tuple[int, int, int]) -> pygame.Surface:
        """Render text and cache it to avoid expensive font.render calls every frame."""
        key = (text, id(font), color)
        if key not in self._text_cache:
            self._text_cache[key] = font.render(text, True, color)
        return self._text_cache[key]

    def draw_panel(
        self,
        x: int,
        y: int,
        lines: list[str],
        color: tuple[int, int, int, int] = PANEL_BG,
        text_color: tuple[int, int, int] = TEXT_MUTED,
        title: Optional[str] = None,
        line_colors: Optional[dict[int, tuple[int, int, int]]] = None,
    ) -> int:
        """Draw a semi-transparent debug panel with optional title and colored lines."""
        line_colors = line_colors or {}
        padding = 12
        line_height = 22
        title_gap = 8

        # 1. Render all text using cache
        rendered_lines = [
            self._render_text(line, self.debug_font,
                              line_colors.get(i, text_color))
            for i, line in enumerate(lines)
        ]

        # 2. Calculate dimensions
        max_w = max((s.get_width() for s in rendered_lines), default=0)
        title_surf = None
        title_block_h = 0

        if title:
            title_surf = self._render_text(title, self.title_font, TEXT_TITLE)
            max_w = max(max_w, title_surf.get_width())
            title_block_h = title_surf.get_height() + title_gap + 1 + title_gap

        panel_w = max_w + padding * 2
        panel_h = title_block_h + len(lines) * line_height + padding * 2

        # 3. Draw background
        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(bg, color, (0, 0, panel_w, panel_h))
        pygame.draw.rect(bg, PANEL_BORDER, (0, 0, panel_w, panel_h), width=1)
        self.display_surface.blit(bg, (x, y))

        # 4. Draw title
        content_y = y + padding
        if title_surf:
            self.display_surface.blit(title_surf, (x + padding, content_y))
            content_y += title_surf.get_height() + title_gap
            pygame.draw.line(
                self.display_surface, PANEL_BORDER,
                (x + padding, content_y), (x + panel_w - padding, content_y), 1
            )
            content_y += title_gap + 1

        # 5. Draw lines
        for i, surf in enumerate(rendered_lines):
            self.display_surface.blit(
                surf, (x + padding, content_y + i * line_height))

        return panel_h + 12

    def draw_state_panel(self, x: int, y: int, player: Any) -> int:
        """Draw state panel for the player."""
        if not player or not getattr(player, "state_machine", None):
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

        line_colors: dict[int, tuple[int, int, int]] = {}
        combat = getattr(player, "combat", None)

        if combat:
            attack_name = combat.state.attack_name if hasattr(
                combat.state, "attack_name") else "-"
            phase_idx = getattr(combat.state, "phase_index", 0)
            total_phases = len(combat.state.current_attack_def.phases) if getattr(
                combat.state, "current_attack_def", None) else 0

            phase_text = f"{phase_idx}/{total_phases-1}" if total_phases > 0 else "idle"
            lines.append(f"Combat {attack_name}  phase {phase_text}")

            hurt_idx = len(lines)
            hurt_timer = getattr(combat, "_hurt_timer", 0.0)
            is_hurt = getattr(combat, "is_hurt", False)
            lines.append(f"Hurt   {is_hurt!s:5} {hurt_timer:.2f}s")
            if is_hurt:
                line_colors[hurt_idx] = TEXT_CRIT

            charging = getattr(combat, "charging", None)
            if charging and getattr(charging, "is_charging", False) and charging.attack_name:
                idx = len(lines)
                lines.append(
                    f"Charge {charging.attack_name} {charging.charge_timer:.2f}s")
                line_colors[idx] = TEXT_WARN

            cooldowns_dict = getattr(combat, "_cooldowns", {})
            cooldowns = [f"{name}:{cd:.2f}s" for name,
                         cd in cooldowns_dict.items() if cd > 0]
            if cooldowns:
                lines.append("CDs    " + ", ".join(cooldowns[:4]))

        stagger_timer = getattr(player, "stagger_timer", 0.0)
        if stagger_timer > 0:
            idx = len(lines)
            lines.append(f"Stagger {stagger_timer:.2f}s")
            line_colors[idx] = TEXT_WARN

        inv_timer = getattr(player, "invincibility_timer", 0.0)
        if inv_timer > 0:
            idx = len(lines)
            lines.append(f"Invincible {inv_timer:.2f}s")
            line_colors[idx] = TEXT_OK

        return self.draw_panel(x, y, lines, title="PLAYER STATE", line_colors=line_colors)

    def draw_stats_panel(self, x: int, y: int, player: Any) -> int:
        """Draw stats panel for the player."""
        if not player:
            return 0

        hp_ratio = player.health / player.max_health if player.max_health else 0
        hp_color = TEXT_OK if hp_ratio > 0.5 else TEXT_WARN if hp_ratio > 0.25 else TEXT_CRIT

        lines = [
            f"HP     {player.health:.0f}/{player.max_health:.0f}",
            f"Block  {player.block_stamina:.2f}/{player.max_block_stamina:.2f}   cd {player.block_cooldown_timer:.2f}s",
            f"Dash   {player.dash_charges}/{player.max_dash_charges}   pen {player.dash_penalty_timer:.2f}s  regen {player.dash_recharge_timer:.2f}s",
            f"Move   spd {player.speed:.0f}  ctrl {player.floor_control:.1f}/{player.air_control:.1f}",
            f"Jump   h {player.jump_height:.0f}  wall {player.wall_jump_height:.0f}",
            f"Dash   spd {player.dash_speed:.0f}  dur {player.dash_duration:.2f}s  fric {player.dash_friction:.1f}",
        ]

        combo = getattr(getattr(player, "combat", None), "combo", None)
        if combo:
            lines.append(
                f"Combo  x{getattr(combo, 'count', 0)}   {getattr(combo, '_timer', 0.0):.2f}s")
        else:
            lines.append("Combo  x0   0.00s")

        return self.draw_panel(x, y, lines, title="STATS", line_colors={0: hp_color})

    def draw_performance_panel(
        self, fps: float, sprite_count: int, combat_count: int,
        entity_count: int, collision_count: int, hit_stop: float, spawn_cd: float
    ) -> None:
        """Draw performance panel at the top right of the screen."""
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

        # Calculate width to position it on the right
        max_w = max(self._render_text(line, self.debug_font,
                    TEXT_MUTED).get_width() for line in lines)
        panel_w = max_w + 24  # 12 * 2 padding
        panel_x = self.display_surface.get_width() - panel_w - 12

        self.draw_panel(panel_x, 12, lines, title="PERFORMANCE",
                        line_colors={0: fps_color})

    def draw_debug_overlays(self, all_sprites: pygame.sprite.Group, camera: Camera) -> None:
        """Draw debug overlays for hitboxes, attack boxes, and entity states."""
        screen_w = self.display_surface.get_width()
        screen_h = self.display_surface.get_height()

        for sprite in all_sprites:
            # 1. Hitboxes & Attack Boxes
            hitbox = getattr(sprite, "hitbox", None)
            if hitbox:
                pygame.draw.rect(self.display_surface,
                                 (100, 140, 160), camera.apply(hitbox), width=1)

            combat = getattr(sprite, "combat", None)
            if combat and getattr(combat, "attack_box", None):
                pygame.draw.rect(self.display_surface, (170, 120, 80),
                                 camera.apply(combat.attack_box), width=2)

            # 2. State Labels
            sm = getattr(sprite, "state_machine", None)
            if not sm:
                continue

            state = sm.current_state_name or "None"
            text = f"{sprite.__class__.__name__}: {state}"

            # Use cached text
            label_surf = self._render_text(text, self.label_font, TEXT_MUTED)

            ref = hitbox if hitbox else sprite.rect
            if not ref:
                continue

            screen_rect = camera.apply(ref)

            # Position label above the entity
            label_rect = label_surf.get_rect(midbottom=(
                screen_rect.centerx, screen_rect.top - 8))

            # Clamp to screen boundaries
            if label_rect.left < 0:
                label_rect.left = 0
            if label_rect.right > screen_w:
                label_rect.right = screen_w
            if label_rect.top < 0:
                label_rect.top = 0

            # Draw label background
            bg_rect = label_rect.inflate(12, 6)
            panel = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (18, 20, 24, 210), (0, 0, *bg_rect.size))
            pygame.draw.rect(panel, PANEL_BORDER,
                             (0, 0, *bg_rect.size), width=1)

            self.display_surface.blit(panel, bg_rect.topleft)
            self.display_surface.blit(label_surf, label_rect.topleft)

    def draw_health_bars(self, entities: pygame.sprite.Group | list, camera: Camera) -> None:
        """Draw a health bar above each entity."""
        for entity in entities:
            if getattr(entity, "is_dead", False):
                continue

            max_hp = getattr(entity, "max_health", 0)
            if not max_hp:
                continue

            hp = getattr(entity, "health", 0)
            rect = getattr(entity, "hitbox", None) or getattr(
                entity, "rect", None)
            if not rect:
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

            # Background
            pygame.draw.rect(self.display_surface, (35, 37, 40), bg_rect)

            # Health fill
            health_ratio = max(0.0, min(1.0, hp / max_hp))
            health_width = bar_width * health_ratio
            color = TEXT_OK if health_ratio > 0.5 else TEXT_WARN if health_ratio > 0.25 else TEXT_CRIT

            if health_width > 0:
                pygame.draw.rect(self.display_surface, color,
                                 (bar_x, bar_y, health_width, bar_height))

            # Border
            pygame.draw.rect(self.display_surface,
                             PANEL_BORDER, bg_rect, width=1)
