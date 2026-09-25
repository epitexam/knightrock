from collections import deque
from time import perf_counter
from typing import Any, cast

import pygame

from src.core.colors import BG_COLORS, Colors
from src.core.level.level_data import LevelConfig
from src.core.settings import Afterimage, HitFlash
from src.core.sprite_groups import SpriteGroups
from src.ui.panel_renderer import PanelLayout
from src.ui.ui_manager import UIManager

HEALTH_BAR_CLEARANCE_PX = 18
# Above either, the partial update costs more than the full refresh it avoids.
DIRTY_RECT_COUNT_LIMIT = 64
DIRTY_AREA_RATIO_LIMIT = 0.6
# An alpha at or above this is a whole tick already elapsed: nothing to blend.
ALPHA_FULL_THRESHOLD = 1.0


def clamp_unit(value: float) -> float:
    """Clamp a tick fraction into [0, 1]."""
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def alpha_is_full(value: float) -> bool:
    """Whether the tick fraction means "a whole tick has already elapsed"."""
    return value >= ALPHA_FULL_THRESHOLD


"""Headroom above each sprite rect where WorldUI draws health bars."""

DASH_STRETCH_X = 1.6
"""Horizontal cartoon stretch applied to dashing players (render-only)."""

DASH_STRETCH_Y = 0.6
"""Vertical squash paired with the dash stretch (render-only)."""

# Chromatic aberration offset for dashing players (simulated via RGB channel separation)
DASH_CHROMATIC_ABERRATION_PX = 2.0
"""Pixel offset for RGB channel separation during dash (render-only)."""


def is_player_dashing(sprite: object) -> bool:
    """Whether the sprite is a player currently in its dash state."""
    if getattr(sprite, "faction", None) != "player":
        return False
    state_machine = getattr(sprite, "state_machine", None)
    return getattr(state_machine, "current_state_name", None) == "dash"


def dash_frame(
    image: pygame.Surface, screen_rect: pygame.Rect, apply_tint: bool = True
) -> tuple[pygame.Surface, pygame.Rect]:
    """Stretch a dash frame wide-and-low, recentered on its screen rect."""
    width = max(1, int(image.get_width() * DASH_STRETCH_X))
    height = max(1, int(image.get_height() * DASH_STRETCH_Y))
    stretched = pygame.transform.scale(image, (width, height))
    # Add energetic cyan tint to dash frame for speed feel
    if apply_tint:
        stretched.fill((100, 200, 255), special_flags=pygame.BLEND_RGB_ADD)
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
        self._ghost_timer: float = 0.0
        # Zoomed sprite surfaces: ``(id(image), zoom) -> (image, scaled)``.
        # Scaling a surface every frame for every visible sprite is expensive,
        # so each (source image, zoom) pair is scaled once and reused. The
        # source is kept *in the cached value* on purpose: a dict key built
        # from ``id(image)`` alone can be hit by a freed surface whose id was
        # recycled, which would hand back a stale, wrongly sized blit.
        self._scaled_cache: dict[tuple[int, float], tuple[pygame.Surface, pygame.Surface]] = {}
        # White damage-flash silhouettes, keyed by ``id(image)`` like
        # ``_scaled_cache`` and holding the source for the same reason.
        self._flash_cache: dict[int, tuple[pygame.Surface, pygame.Surface]] = {}
        self._dashing_player: object | None = None
        # Render interpolation: how far the presentation sits into the current
        # tick, in [0, 1], fed from the loop's accumulator.
        self.alpha = 0.0
        self._previous_positions: dict[int, pygame.Rect] = {}
        self._sim_rects: list[pygame.Rect] = []
        self._debug_samples: dict[str, deque[float]] = {
            "world_ui_ms": deque(maxlen=120),
            "panels_ms": deque(maxlen=120),
        }

    def set_display_surface(self, display_surface: pygame.Surface) -> None:
        self.display_surface = display_surface
        self.ui_manager.set_display_surface(display_surface)
        self.camera.set_viewport_size(display_surface.get_width(), display_surface.get_height())
        self._previous_dirty.clear()
        self._scaled_cache.clear()
        self._flash_cache.clear()

    def _scaled_image(self, image: pygame.Surface) -> pygame.Surface:
        """Scale ``image`` by the camera zoom, caching the result.

        Returns the image untouched when the zoom is 1 (the previous, unzoomed
        behaviour) so a de-zoomed build never pays for scaling.
        """
        zoom = self.camera.zoom
        if zoom == 1.0:
            return image
        key = (id(image), zoom)
        cached = self._scaled_cache.get(key)
        if cached is not None:
            return cached[1]
        width = max(1, round(image.get_width() * zoom))
        height = max(1, round(image.get_height() * zoom))
        scaled = (
            pygame.transform.smoothscale(image, (width, height))
            if zoom > 1.0
            else pygame.transform.scale(image, (width, height))
        )
        self._scaled_cache[key] = (image, scaled)
        return scaled

    def _white_silhouette(self, image: pygame.Surface) -> pygame.Surface:
        """A white copy of ``image`` keeping its alpha, memoised per image.

        Building a mask and converting it to a surface costs 6.8us, and a
        flashing entity redraws for the whole 0.1s of its flash, so this was
        the most expensive per-sprite operation on the hit-feedback path. The
        silhouette only depends on the source image, never on the flash
        intensity, so it is built once per image and the caller copies it to
        set its own alpha.

        The source is kept in the cached value: an ``id``-keyed dict can be
        handed a freed surface whose id was recycled, which would return a
        silhouette of the wrong size.
        """
        key = id(image)
        cached = self._flash_cache.get(key)
        if cached is not None:
            return cached[1]
        mask = pygame.mask.from_surface(image)
        silhouette = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
        self._flash_cache[key] = (image, silhouette)
        return silhouette

    def _scaled_image_once(self, image: pygame.Surface) -> pygame.Surface:
        """Scale a transient surface by the zoom, without caching it.

        Afterimages and damage flashes build a brand new surface every frame,
        so caching them by ``id()`` would grow the cache forever. They are
        short-lived by nature, so scaling them directly is both correct and
        cheap enough.
        """
        zoom = self.camera.zoom
        if zoom == 1.0:
            return image
        width = max(1, round(image.get_width() * zoom))
        height = max(1, round(image.get_height() * zoom))
        if zoom > 1.0:
            return pygame.transform.smoothscale(image, (width, height))
        return pygame.transform.scale(image, (width, height))

    def _record_debug_sample(self, name: str, elapsed_ms: float) -> None:
        self._debug_samples[name].append(elapsed_ms)

    def debug_metrics_snapshot(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for name, samples in self._debug_samples.items():
            ordered = sorted(samples)
            result[name] = ordered[-1] if ordered else 0.0
            index = min(len(ordered) - 1, int(len(ordered) * 0.95)) if ordered else 0
            result[f"{name.removesuffix('_ms')}_p95_ms"] = ordered[index] if ordered else 0.0
        return result

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

    def draw(
        self,
        groups: SpriteGroups,
        debug_enabled: bool = False,
        dt: float = 0.0,
        alpha: float = 0.0,
    ):
        """Draw the world; return dirty rects, or None for a full refresh.

        ``alpha`` is the position within the current simulation tick, in
        [0, 1]. It is passed rather than read from the clock so the blend is
        a pure function of the loop state and stays reproducible.
        """
        self.alpha = clamp_unit(alpha)
        # One transform for the whole pass: ``is_visible``/``apply`` run once
        # per visible sprite and the camera cannot move mid-draw.
        self.camera.begin_frame()
        self._dashing_player = self._find_dashing_player(groups)
        blits = self._collect_visible_blits(groups)
        ghost_draws = self._update_afterimages(groups, dt)
        flashes = self._collect_flashes(groups)
        if debug_enabled:
            self._draw_full(groups, blits)
            self._draw_ghosts(ghost_draws)
            self._draw_flashes(flashes)
            started = perf_counter()
            self.ui_manager.draw_debug_overlays(groups.all_sprites, self.camera, dt)
            self._record_debug_sample("world_ui_ms", (perf_counter() - started) * 1000.0)
            return None

        dirty = [self._to_dirty_rect(screen_rect) for _, screen_rect in blits]
        # An interpolated sprite is blitted partway between two ticks, but the
        # overlays drawn on top of it (HP bars) and the next tick's blit both
        # use the simulation's own rect, so the region it will occupy has to be
        # refreshed too. Deduplicated because a sprite that did not move this
        # frame has one rect, not two.
        dirty += [
            self._to_dirty_rect(rect)
            for rect in self._sim_rects
            if not any(rect == screen for _, screen in blits)
        ]
        dirty += [self._to_dirty_rect(screen_rect) for _, screen_rect in ghost_draws]
        update_rects = [*dirty, *self._previous_dirty]
        self._previous_dirty = dirty
        area = update_rects[0].unionall(update_rects[1:]) if update_rects else None
        if area is not None and self._exceeds_dirty_budget(area, len(update_rects)):
            # The union covers most of the screen: the per-rect bookkeeping
            # and SDL's per-rect present cost are then pure overhead, since
            # filling the whole screen and blitting what is visible is both
            # simpler and cheaper. Measured on a viewport-filling scene this
            # hybrid was ~10% *slower* than the plain full refresh it was
            # meant to avoid.
            self.display_surface.fill(self.background_color)
            self._draw_ghosts(ghost_draws)
            for surface, screen_rect in blits:
                self.display_surface.blit(surface, screen_rect)
            self._draw_flashes(flashes)
            return None
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

    def _find_dashing_player(self, groups: SpriteGroups) -> object | None:
        """The one sprite that can be a dashing player, or None.

        ``is_player_dashing`` needs three attribute lookups to answer, and
        ``_collect_visible_blits`` used to ask it of every visible sprite on
        the level -- about a thousand, to find at most one. Resolving it once
        turns that into an identity comparison in the blit loop.
        """
        for sprite in groups.entity_sprites:
            if is_player_dashing(sprite):
                return cast("pygame.sprite.Sprite", sprite)
        return None

    def _exceeds_dirty_budget(self, area: pygame.Rect, rect_count: int) -> bool:
        """Whether the partial update has stopped being worth its cost.

        Dirty rects pay off when little of the screen changes. They stop
        paying off as soon as their union approaches the whole viewport: the
        region is then filled, culled and blitted almost as if there were no
        dirty tracking, plus a per-rect cost on the present. Both guards are
        deliberately loose -- this only has to catch the degenerate case, not
        to micro-tune the crossover.
        """
        if rect_count > DIRTY_RECT_COUNT_LIMIT:
            return True
        surface_area = self.display_surface.get_width() * self.display_surface.get_height()
        if surface_area <= 0:
            return False
        return bool(area.width * area.height > surface_area * DIRTY_AREA_RATIO_LIMIT)

    def _interpolated_rect(self, sprite, screen_rect: pygame.Rect) -> pygame.Rect:
        """``screen_rect`` moved to partway between the last two ticks.

        The simulation is fixed-step while the presentation is not, so the
        position a tick wrote is on average half a tick stale and gets shown
        twice whenever two ticks run per frame. Blending towards the next
        tick's position removes that judder.

        A sprite with no recorded previous position -- freshly spawned, or
        not moved by the last tick -- is drawn where it is, so nothing ever
        interpolates in from the origin.
        """
        previous = self._previous_positions.get(id(sprite))
        if previous is None or alpha_is_full(self.alpha):
            return screen_rect
        if previous == screen_rect:
            return screen_rect
        return pygame.Rect(
            previous.x + (screen_rect.x - previous.x) * self.alpha,
            previous.y + (screen_rect.y - previous.y) * self.alpha,
            screen_rect.width,
            screen_rect.height,
        )

    def _remember_positions(self, blits, sprites) -> None:
        """Record this frame's screen rects as next frame's starting point."""
        remembered: dict[int, pygame.Rect] = {}
        for sprite, (_, screen_rect) in zip(sprites, blits, strict=False):
            remembered[id(sprite)] = screen_rect
        self._previous_positions = remembered

    def _collect_visible_blits(self, groups: SpriteGroups):
        """Camera-cull and compute screen rects for every visible plane.

        The FX plane is deliberately *not* scaled through ``_scaled_image``:
        FX particles rebuild their ``image`` every tick, so each one is a new
        Surface object and each one would add a permanent entry to the scale
        cache. Caching them grew the cache by one retained surface per FX
        sprite per tick, for the whole session, with no eviction. They are
        short-lived by nature, so they go through ``_scaled_image_once``.
        """
        blits: list[tuple[pygame.Surface, pygame.Rect]] = []
        culled: list[object] = []
        self._sim_rects = []
        cached_planes = (*groups.all_sprites, *groups.fg_sprites)
        for sprite in cached_planes:
            if self.camera.is_visible(sprite.rect):
                sim_rect = self._screen_rect(sprite)
                self._sim_rects.append(sim_rect)
                screen_rect = self._interpolated_rect(sprite, sim_rect)
                culled.append(sprite)
                image = self._scaled_image(sprite.image)
                # Only a player can be dashing, and a player is an entity, so
                # this branch is resolved by identity rather than by a
                # ``getattr`` walk over every tile of the level.
                if self._dashing_player is not None and sprite is self._dashing_player:
                    blits.append(dash_frame(image, screen_rect))
                else:
                    blits.append((image, screen_rect))
        for sprite in groups.fx_sprites:
            if self.camera.is_visible(sprite.rect):
                screen_rect = pygame.Rect(self.camera.apply(sprite.rect))
                blits.append((self._scaled_image_once(sprite.image), screen_rect))
        self._remember_positions(blits, culled)
        return blits

    def _screen_rect(self, sprite) -> pygame.Rect:
        return pygame.Rect(self.camera.apply(sprite.rect))

    def _collect_flashes(self, groups: SpriteGroups):
        """White damage-flash overlays for recently hit entities.

        Only entities can flash (they are the only ones with a
        ``flash_timer``), so this walks ``entity_sprites``: scanning
        ``all_sprites`` cost a ``getattr`` on every tile of the level, ~1000
        of them, to find at most a handful of flashes.
        """
        flashes: list[tuple[pygame.Surface, pygame.Rect]] = []
        for sprite in groups.entity_sprites:
            timer = float(getattr(sprite, "flash_timer", 0.0) or 0.0)
            if timer <= 0.0 or not self.camera.is_visible(sprite.rect):
                continue
            overlay = self._white_silhouette(sprite.image)
            overlay = overlay.copy()
            overlay.set_alpha(int(255 * min(1.0, timer / HitFlash.DURATION)))
            screen_rect = pygame.Rect(self.camera.apply(sprite.rect))
            overlay = self._scaled_image_once(overlay)
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
        """Snapshot dashing players into fading ghosts.

        The dashing player is an entity, so this walks ``entity_sprites``
        rather than the whole level: ``all_sprites`` meant a full-group
        ``is_player_dashing`` scan several times a second.
        """
        for sprite in groups.entity_sprites:
            if not is_player_dashing(sprite):
                continue
            if not self.camera.is_visible(sprite.rect):
                continue
            ghost = sprite.image.copy()
            # Speed tint: the trail reads as energy, not a plain snapshot.
            ghost.fill((170, 220, 255), special_flags=pygame.BLEND_RGB_MULT)
            # Zoom before the dash stretch: ``dash_frame`` sizes itself from the
            # image, so a world-sized ghost would stay small on screen.
            ghost = self._scaled_image_once(ghost)
            screen_rect = pygame.Rect(self.camera.apply(sprite.rect))
            ghost, ghost_rect = dash_frame(ghost, screen_rect, apply_tint=False)
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

    def draw_health_bars(self, entities) -> list[pygame.Rect]:
        """Draw the HP bars; return the rects they occupy, to be presented."""
        return self.ui_manager.draw_health_bars(entities, self.camera)

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
        cache_size: int | None = None,
    ):
        started = perf_counter()
        self.ui_manager.renderer.interaction.begin_frame()
        if not self.ui_manager.world_ui.layers.get("panels", True):
            self._record_debug_sample("panels_ms", 0.0)
            return
        surface = self.ui_manager.renderer.display_surface
        layout = PanelLayout(surface.get_width(), surface.get_height())
        # PERFORMANCE is pinned first so the column flow can reserve it and
        # wrap around it; COMBAT counters then lead the flow, so the tall
        # PLAYER STATE / STATS panels can never overdraw them.
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
            layout=layout,
            debug_stats=self.debug_metrics_snapshot(),
        )
        compact = surface.get_width() < 1100 or surface.get_height() < 800
        if compact:
            self.ui_manager.draw_compact_panel(player, layout, game)
        else:
            self.ui_manager.draw_combat_panel(layout)
            self.ui_manager.draw_state_panel(10, 10, player, layout=layout)
            self.ui_manager.draw_stats_panel(10, 10, player, layout=layout)
            if game is not None:
                self.ui_manager.draw_scene_panel(10, 10, game, layout=layout)
            self.ui_manager.draw_help_panel(
                10, 10, layout=layout, layers=self.ui_manager.world_ui.layers
            )
            self.ui_manager.draw_legend_panel(10, 10, layout=layout)
        self._record_debug_sample("panels_ms", (perf_counter() - started) * 1000.0)
