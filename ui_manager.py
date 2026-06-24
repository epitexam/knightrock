"""
User interface management (debugging panels, statistics, overlays)
"""

import pygame
from colors import Colors


class UIManager:
    """Draws the various information panels and debugging overlays."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        self.display_surface = display_surface
        self.debug_font = pygame.font.SysFont("Arial", 24)
        self.label_font = pygame.font.SysFont("Arial", 16)

    def draw_panel(
        self, x: int, y: int, lines: list[str], color: tuple, text_color: tuple
    ) -> int:
        """Draw a generic panel and return its height."""
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
        """Player state machine status panel."""
        if player is None or player.state_machine is None:
            return 0

        sm = player.state_machine
        current = sm.current_state_name or "None"
        previous = sm.previous_state_name or "—"
        history = sm.history[-6:] if sm.history else []

        lines = [
            f"State:  {current}",
            f"Prev:   {previous}",
            f"Hist:   {' → '.join(history)}",
            f"Vel:    ({player.velocity.x:.1f}, {player.velocity.y:.1f})",
            f"Floor: {player.on_surface['floor']}   L: {player.on_surface['left']}   R: {player.on_surface['right']}",
        ]
        if player.combat.is_attacking:
            lines.append(f"Attack: {player.combat.current_attack}")

        return self.draw_panel(x, y, lines, (0, 0, 0, 180), Colors.white)

    def draw_stats_panel(self, x: int, y: int, player) -> int:
        """Player resource panel (HP, block, dash)."""
        if player is None:
            return 0

        p = player
        lines = [
            f"HP:    {getattr(p, 'health', 100):.0f}",
            f"Block: {p.block_stamina:.2f}/{p.max_block_stamina:.2f}   CD: {p.block_cooldown_timer:.2f}s",
            f"Dash:  {p.dash_charges}/{p.max_dash_charges}   Pen: {p.dash_penalty_timer:.2f}s   Regen: {p.dash_recharge_timer:.2f}s",
        ]
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
        """Performance panel at the top right."""
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

    def draw_debug_overlays(self, all_sprites: pygame.sprite.Group) -> None:
        """Draw the hitboxes, attack boxes, and state labels."""
        for sprite in all_sprites:
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
            bg = label_surf.get_rect(midbottom=(ref.centerx, ref.top - 8))
            bg.left = max(0, min(bg.left, self.display_surface.get_width() - bg.width))
            bg.top = max(0, bg.top)

            pygame.draw.rect(self.display_surface, (0, 0, 0, 160), bg, border_radius=4)
            self.display_surface.blit(label_surf, bg)
