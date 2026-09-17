from typing import Any

import pygame

from src.core.colors import BG_COLORS, Colors
from src.core.level.level_data import LevelConfig
from src.core.settings import Afterimage, HitFlash
from src.core.sprite_groups import SpriteGroups
from src.ui.ui_manager import UIManager

HEALTH_BAR_CLEARANCE_PX = 18
"""Headroom above each sprite rect where WorldUI draws health bars."""

DASH_STRETCH_X = 1.28
"""Horizontal cartoon stretch applied to dashing players (render-only)."""

DASH_STRETCH_Y = 0.78
"""Vertical squash paired with the dash stretch (render-only)."""


def is_player_dashing(sprite: object) -> bool:
    """Whether the sprite is a player currently in its dash state."""
    if getattr(sprite, "faction", None) != "player":
        return False
    state_machine = getattr(sprite, "state_machine", None)
    return getattr(state_machine, "current_state_name", None) == "dash"


def dash_frame(
    image: pygame.Surface, screen_rect: pygame.Rect
) -> tuple[pygame.Surface, pygame.Rect]:
    """Stretch a dash frame wide-and-low, recentered on its screen rect."""
    width = max(1, int(image.get_width() * DASH_STRETCH_X))
    height = max(1, int(image.get_height() * DASH_STRETCH_Y))
    stretched = pygame.transform.scale(image, (width, height))
    return stretched, stretched.get_rect(center=screen_rect.center)


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
        self._ghosts: list[tuple[pygame.Surface, pygame.Rect, float]] = []
        self._ghost_timer = 0.0

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

    def draw(self, groups: SpriteGroups, debug_enabled: bool = False, dt: float = 0.0):
        """Draw the world; return dirty rects, or None for a full refresh."""
        blits = self._collect_visible_blits(groups)
        ghost_draws = self._update_afterimages(groups, dt)
        flashes = self._collect_flashes(groups)
        dirty = [self._to_dirty_rect(screen_rect) for _, screen_rect in blits]
        dirty += [self._to_dirty_rect(screen_rect) for _, screen_rect in ghost_draws]

        update_rects = [*dirty, *self._previous_dirty]
        self._previous_dirty = dirty

        if debug_enabled:
            self._draw_full(groups, blits)
            self._draw_ghosts(ghost_draws)
            self._draw_flashes(flashes)
            self.ui_manager.draw_debug_overlays(groups.all_sprites, self.camera)
            return None

        area = update_rects[0].unionall(update_rects[1:]) if update_rects else None
        if area is not None:
            # Erase exactly the region that will be refreshed: every pixel
            # that changed since the last presented frame is repainted.
            self.display_surface.fill(self.background_color, area)
            self._draw_ghosts(ghost_draws, area)
            for surface, screen_rect in blits:
                if area.colliderect(screen_rect):
                    self.display_surface.blit(surface, screen_rect)
            self._draw_flashes(flashes, area)
        return update_rects

    def _collect_visible_blits(self, groups: SpriteGroups):
        """Camera-cull and compute screen rects for every visible plane."""
        blits: list[tuple[pygame.Surface, pygame.Rect]] = []
        for sprite in (*groups.all_sprites, *groups.fg_sprites, *groups.fx_sprites):
            if self.camera.is_visible(sprite.rect):
                screen_rect = pygame.Rect(self.camera.apply(sprite.rect))
                if is_player_dashing(sprite):
                    blits.append(dash_frame(sprite.image, screen_rect))
                else:
                    blits.append((sprite.image, screen_rect))
        return blits

    def _collect_flashes(self, groups: SpriteGroups):
        """White damage-flash overlays for recently hit entities."""
        flashes: list[tuple[pygame.Surface, pygame.Rect]] = []
        for sprite in (*groups.all_sprites, *groups.fg_sprites):
            timer = float(getattr(sprite, "flash_timer", 0.0) or 0.0)
            if timer <= 0.0 or not self.camera.is_visible(sprite.rect):
                continue
            mask = pygame.mask.from_surface(sprite.image)
            overlay = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
            overlay.set_alpha(int(255 * min(1.0, timer / HitFlash.DURATION)))
            screen_rect = pygame.Rect(self.camera.apply(sprite.rect))
            if is_player_dashing(sprite):
                overlay, screen_rect = dash_frame(overlay, screen_rect)
            flashes.append((overlay, screen_rect))
        return flashes

    def _draw_flashes(self, flashes, area=None) -> None:
        for overlay, screen_rect in flashes:
            if area is None or area.colliderect(screen_rect):
                self.display_surface.blit(overlay, screen_rect)

    def _update_afterimages(self, groups: SpriteGroups, dt: float):
        """Maintain the dash ghost trail (render-only, capped + fading)."""
        live: list[tuple[pygame.Surface, pygame.Rect, float]] = []
        for surface, screen_rect, ttl in self._ghosts:
            ttl -= dt
            if ttl > 0.0:
                surface.set_alpha(int(255 * ttl / Afterimage.TTL))
                live.append((surface, screen_rect, ttl))
        self._ghosts = live
        if dt > 0.0:
            self._ghost_timer += dt
            if self._ghost_timer >= Afterimage.SPAWN_EVERY:
                self._ghost_timer = 0.0
                self._spawn_afterimage(groups)
        return [(surface, screen_rect) for surface, screen_rect, _ in self._ghosts]

    def _spawn_afterimage(self, groups: SpriteGroups) -> None:
        """Snapshot dashing players into fading ghosts."""
        for sprite in groups.all_sprites:
            if not is_player_dashing(sprite):
                continue
            if not self.camera.is_visible(sprite.rect):
                continue
            ghost = sprite.image.copy()
            # Speed tint: the trail reads as energy, not a plain snapshot.
            ghost.fill((170, 220, 255), special_flags=pygame.BLEND_RGB_MULT)
            screen_rect = pygame.Rect(self.camera.apply(sprite.rect))
            ghost, ghost_rect = dash_frame(ghost, screen_rect)
            self._ghosts.append((ghost, ghost_rect, Afterimage.TTL))
            self._ghosts = self._ghosts[-Afterimage.MAX :]

    def _draw_ghosts(self, ghost_draws, area=None) -> None:
        for surface, screen_rect in ghost_draws:
            if area is None or area.colliderect(screen_rect):
                self.display_surface.blit(surface, screen_rect)

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
        game: Any = None,
        frame_time: float = 0.0,
        cache_size: int = 0,
    ):
        if not self.ui_manager.world_ui.layers.get("panels", True):
            return
        x, y = 10, 10
        y += self.ui_manager.draw_state_panel(x, y, player) + 8
        y += self.ui_manager.draw_stats_panel(x, y, player) + 8
        if game is not None:
            y += self.ui_manager.draw_scene_panel(x, y, game) + 8
        y += self.ui_manager.draw_help_panel(x, y) + 8
        self.ui_manager.draw_performance_panel(
            fps=fps,
            sprite_count=sprite_count,
            combat_count=combat_count,
            entity_count=entity_count,
            collision_count=collision_count,
            hit_stop=hit_stop,
            spawn_cooldown=spawn_cooldown,
            frame_time=frame_time,
            cache_size=cache_size,
        )
