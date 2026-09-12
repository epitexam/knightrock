import pygame

from src.core.colors import BG_COLORS, Colors
from src.core.level.level_data import LevelConfig
from src.core.sprite_groups import SpriteGroups
from src.ui.ui_manager import UIManager

HEALTH_BAR_CLEARANCE_PX = 18
"""Headroom above each sprite rect where WorldUI draws health bars."""


class Renderer:
    """World renderer with dirty-rect presentation (Phase 2 #2).

    ``draw`` returns the list of screen rects that changed this frame
    (this frame's blits unioned with the previous frame's), so the game
    loop can call :func:`pygame.display.update` with exactly those rects
    instead of flipping the whole 1440x900 surface.  Debug mode redraws
    everything and returns ``None`` (full-screen update).
    """

    def __init__(self, display_surface, camera, config: LevelConfig | None = None):
        self.display_surface = display_surface
        self.camera = camera
        self.ui_manager = UIManager(display_surface)
        self.background_color = self._resolve_background_color(config)
        self._previous_dirty: list[pygame.Rect] = []

    @staticmethod
    def _resolve_background_color(config):
        if config is not None and config.bg:
            color = BG_COLORS.get(config.bg)
            if color is not None:
                return color
        return Colors.sky_blue

    @staticmethod
    def _to_dirty_rect(rect) -> pygame.Rect:
        """Convert a world-space FRect to an int screen rect with headroom."""
        dirty = pygame.Rect(rect)
        dirty.top -= HEALTH_BAR_CLEARANCE_PX
        dirty.height += HEALTH_BAR_CLEARANCE_PX
        return dirty

    def draw(self, groups: SpriteGroups, debug_enabled: bool = False):
        """Draw the world; return dirty rects, or None for a full refresh."""
        blits = self._collect_visible_blits(groups)
        dirty = [self._to_dirty_rect(screen_rect) for _, screen_rect in blits]

        update_rects = [*dirty, *self._previous_dirty]
        self._previous_dirty = dirty

        if debug_enabled:
            self._draw_full(groups, blits)
            self.ui_manager.draw_debug_overlays(groups.all_sprites, self.camera)
            return None

        area = update_rects[0].unionall(update_rects[1:]) if update_rects else None
        if area is not None:
            # Erase exactly the region that will be refreshed: every pixel
            # that changed since the last presented frame is repainted.
            self.display_surface.fill(self.background_color, area)
            for surface, screen_rect in blits:
                if area.colliderect(screen_rect):
                    self.display_surface.blit(surface, screen_rect)
        return update_rects

    def _collect_visible_blits(self, groups: SpriteGroups):
        """Camera-cull and compute screen rects for both sprite planes."""
        blits: list[tuple[pygame.Surface, pygame.Rect]] = []
        for sprite in (*groups.all_sprites, *groups.fg_sprites):
            if self.camera.is_visible(sprite.rect):
                screen_rect = self.camera.apply(sprite.rect)
                blits.append((sprite.image, pygame.Rect(screen_rect)))
        return blits

    def _draw_full(self, groups: SpriteGroups, blits) -> None:
        """Full-screen repaint (debug mode or fallback)."""
        self.display_surface.fill(self.background_color)
        for surface, screen_rect in blits:
            self.display_surface.blit(surface, screen_rect)

    def draw_health_bars(self, entities) -> None:
        self.ui_manager.draw_health_bars(entities, self.camera)

    def draw_debug_panels(
        self,
        player,
        fps,
        sprite_count,
        combat_count,
        entity_count,
        collision_count,
        hit_stop,
        spawn_cooldown,
    ):
        x, y = 10, 10
        y += self.ui_manager.draw_state_panel(x, y, player) + 8
        self.ui_manager.draw_stats_panel(x, y, player)
        self.ui_manager.draw_performance_panel(
            fps=fps,
            sprite_count=sprite_count,
            combat_count=combat_count,
            entity_count=entity_count,
            collision_count=collision_count,
            hit_stop=hit_stop,
            spawn_cooldown=spawn_cooldown,
        )
