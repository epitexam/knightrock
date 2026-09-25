from collections import deque
from collections.abc import Iterable, Sequence
from time import perf_counter
from typing import Any, cast

import pygame

from src.core.colors import BG_COLORS, Color, Colors
from src.core.level.level_data import LevelConfig
from src.core.rendering.camera import Camera
from src.core.settings import Afterimage, HitFlash
from src.core.sprite_groups import SpriteGroups
from src.ui.panel_renderer import PanelLayout
from src.ui.ui_manager import UIManager

# The HP bar sits this far above the entity and is this tall; the dirty rect
# of every sprite has to leave room for both on every side, because a bar
# wider than a narrow sprite overhangs it and flips below near the screen top.
HEALTH_BAR_HEIGHT = 6
HEALTH_BAR_ANCHOR_GAP = 8
HEALTH_BAR_SIDE_CLEARANCE_PX = 30
HEALTH_BAR_CLEARANCE_PX = HEALTH_BAR_ANCHOR_GAP + HEALTH_BAR_HEIGHT
# Above either, the partial update costs more than the full refresh it avoids.
DIRTY_RECT_COUNT_LIMIT = 64
DIRTY_AREA_RATIO_LIMIT = 0.6


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

    def __init__(
        self,
        display_surface: pygame.Surface,
        camera: Camera,
        config: LevelConfig | None = None,
    ) -> None:
        self.display_surface = display_surface
        self.camera = camera
        self.ui_manager = UIManager(display_surface)
        self.background_color = self._resolve_background_color(config)
        self._previous_dirty: list[pygame.Rect] = []
        self._ghosts: list[tuple[pygame.Surface, pygame.FRect, float]] = []
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
        self._barrows: list[tuple[pygame.Surface, pygame.Rect, bool]] = []
        # Rects painted after the world pass (HUD, HP bars); folded into the
        # erase and the present on the next frame. See add_overlay_rects.
        self._overlay_rects: list[pygame.Rect] = []
        self._previous_overlay_rects: list[pygame.Rect] = []
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
    def _resolve_background_color(config: LevelConfig | None) -> Color:
        if config is not None and config.bg:
            color = BG_COLORS.get(config.bg)
            if color is not None:
                return color
        return Colors.sky_blue

    @staticmethod
    def _to_dirty_rect(rect: pygame.Rect | pygame.FRect, headroom: bool = False) -> pygame.Rect:
        """Convert a world-space rect to an int screen rect with headroom.

        ``headroom`` is only what the HP bar above the entity needs, and only
        the sprite that actually draws a bar asks for it. A bar is 30px wide
        at minimum and centred on the sprite, so a narrow entity is narrower
        than its own bar; and near the top of the screen the bar flips below
        the entity rather than above. With headroom only on the top edge, the
        bar was painted outside the region the next frame erases, leaving a
        6px-tall stripe of bar-coloured pixels behind every moving enemy.
        """
        dirty = pygame.Rect(rect)
        if not headroom:
            return dirty
        # Not an inflate: the bar needs a *full* gap on each side, and it can
        # sit either above or below the entity. A bar is 30px wide and
        # centred, so a narrow entity must grow by half its overhang per side.
        overhang = max(0, (HEALTH_BAR_SIDE_CLEARANCE_PX - dirty.width) // 2)
        vertical = HEALTH_BAR_HEIGHT + HEALTH_BAR_ANCHOR_GAP
        return pygame.Rect(
            dirty.left - overhang,
            dirty.top - vertical,
            dirty.width + overhang * 2,
            dirty.height + vertical * 2,
        )

    def draw(
        self,
        groups: SpriteGroups,
        debug_enabled: bool = False,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> list[pygame.Rect] | None:
        """Draw the world; return dirty rects, or None for a full refresh.

        ``alpha`` is the position within the current simulation tick, in
        [0, 1]. It is passed rather than read from the clock so the blend is
        a pure function of the loop state and stays reproducible. The camera
        applies it, so every sprite, the HP bars and the debug overlay read
        one transform and cannot drift apart.
        """
        self.camera.begin_frame(alpha)
        # Fresh pass: the overlay rects are re-declared by the callers after
        # this world draw (the HUD and the HP bars), so start from empty.
        self.clear_overlay_rects()
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

        # A sprite that carries an HP bar needs room for it: the bar is 30px
        # wide, centred, and flips below near the top of the screen.
        dirty = [
            self._to_dirty_rect(screen_rect, headroom) for _, screen_rect, headroom in self._barrows
        ]
        dirty += [self._to_dirty_rect(screen_rect) for _, screen_rect in ghost_draws]
        # Overlay rects painted after the last world pass (HUD, HP bars) and
        # their previous position are refreshed too, so a shrinking gauge or a
        # moving bar is erased instead of leaving a stripe behind.
        update_rects = [
            *dirty,
            *self._previous_dirty,
            *self._previous_overlay_rects,
        ]
        self._previous_dirty = dirty
        self._previous_overlay_rects = self._overlay_rects
        area = update_rects[0].unionall(update_rects[1:]) if update_rects else None
        if area is not None and self._must_refresh_fully(area, len(update_rects)):
            # Erase exactly the region that will be refreshed: every pixel
            # that changed since the last presented frame is repainted.
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

    def add_overlay_rects(self, rects: Sequence[pygame.Rect]) -> None:
        """Declare screen rects painted on top of this frame's world pass.

        The world fill erases the union of the sprite rects, and
        ``pygame.display.update`` presents the per-sprite rects. Anything
        painted on top afterwards -- the HUD gauges, the world HP bars -- lives
        outside that union: it is written to the surface, but on the next frame
        the erase never reaches it and it is never re-presented, so a gauge
        that shrinks leaves its old pixels behind as a stripe of stale colour.
        Registering the rects here folds them into both the erase and the
        present on the following frame, so the area painted and the area
        refreshed always agree.
        """
        self._overlay_rects.extend(rects)

    def clear_overlay_rects(self) -> None:
        """Drop the declared overlay rects (start of a fresh pass)."""
        self._overlay_rects = []

    def _find_dashing_player(self, groups: SpriteGroups) -> pygame.sprite.Sprite | None:
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

    def _must_refresh_fully(self, area: pygame.Rect, rect_count: int) -> bool:
        """Whether the frame must repaint the whole surface instead of a region.

        Two reasons, and the second is the one that matters here.

        The obvious one: once the union approaches the viewport, the frame is
        filled, culled and blitted almost as if there were no dirty tracking,
        plus a per-rect cost on the present. Measured on a viewport-filling
        scene the partial path was ~10% *slower* than the plain full refresh
        it was meant to avoid.

        The other: the HUD and the HP bars are painted *after* this pass
        decides what to present, so their rects can only enter the set on the
        following frame. Presenting a region while they sit outside it is how
        they end up one frame stale -- a band along the bottom of the window
        that flickers between the old and the new gauge. The HUD is always on
        screen during gameplay, so a frame carrying overlay rects is not
        allowed to take the partial path at all.
        """
        if self._overlay_rects or self._previous_overlay_rects:
            return True
        return self._exceeds_dirty_budget(area, rect_count)

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

    def _collect_visible_blits(
        self, groups: SpriteGroups
    ) -> list[tuple[pygame.Surface, pygame.Rect]]:
        """Camera-cull and compute screen rects for every visible plane.

        Also fills ``_barrows`` with each blit and whether its dirty rect needs
        HP-bar headroom, so the two can never disagree about which sprite owns
        a bar.

        The FX plane is deliberately *not* scaled through ``_scaled_image``:
        FX particles rebuild their ``image`` every tick, so each one is a new
        Surface object and each one would add a permanent entry to the scale
        cache. Caching them grew the cache by one retained surface per FX
        sprite per tick, for the whole session, with no eviction. They are
        short-lived by nature, so they go through ``_scaled_image_once``.
        """
        blits: list[tuple[pygame.Surface, pygame.Rect]] = []
        barrows: list[tuple[pygame.Surface, pygame.Rect, bool]] = []
        # A sprite whose dirty rect needs HP-bar headroom. Only the entities
        # that ``draw_health_bars`` will actually bar: widening every terrain
        # tile by 30px on each side would be pure overdraw, ~900 times a level.
        cached_planes = (*groups.all_sprites, *groups.fg_sprites)
        for sprite in cached_planes:
            if self.camera.is_visible(sprite.rect):
                headroom = self._has_health_bar(sprite)
                screen_rect = self._screen_rect(sprite)
                image = self._scaled_image(sprite.image)
                # Only a player can be dashing, and a player is an entity, so
                # this branch is resolved by identity rather than by a
                # ``getattr`` walk over every tile of the level.
                if self._dashing_player is not None and sprite is self._dashing_player:
                    image, screen_rect = dash_frame(image, screen_rect)
                blits.append((image, screen_rect))
                barrows.append((image, screen_rect, headroom))
        for sprite in groups.fx_sprites:
            if self.camera.is_visible(sprite.rect):
                screen_rect = self.camera.apply_covering(sprite.rect)
                surface = self._scaled_image_once(sprite.image)
                blits.append((surface, screen_rect))
                barrows.append((surface, screen_rect, False))
        self._barrows = barrows
        return blits

    @staticmethod
    def _has_health_bar(sprite: pygame.sprite.Sprite) -> bool:
        """Whether ``draw_health_bars`` will paint a bar over this sprite.

        Mirrors the gate in ``WorldUI._has_health_bar`` so the dirty rect is
        widened for exactly the sprites that get a bar. A sprite whose bar is
        skipped must not pay the 30px side clearance.
        """
        if getattr(sprite, "faction", None) == "player":
            return False
        if getattr(sprite, "is_dead", False):
            return False
        return bool(getattr(sprite, "max_health", 0))

    def _screen_rect(self, sprite: pygame.sprite.Sprite) -> pygame.Rect:
        rect = sprite.rect
        if rect is None:
            return pygame.Rect(0, 0, 0, 0)
        return self.camera.apply_covering(pygame.FRect(rect))

    def _collect_flashes(self, groups: SpriteGroups) -> list[tuple[pygame.Surface, pygame.Rect]]:
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
            screen_rect = self.camera.apply_covering(sprite.rect)
            overlay = self._scaled_image_once(overlay)
            if is_player_dashing(sprite):
                overlay, screen_rect = dash_frame(overlay, screen_rect)
            flashes.append((overlay, screen_rect))
        return flashes

    def _draw_flashes(
        self,
        flashes: list[tuple[pygame.Surface, pygame.Rect]],
        area: pygame.Rect | None = None,
    ) -> None:
        for overlay, screen_rect in flashes:
            if area is None or area.colliderect(screen_rect):
                self.display_surface.blit(overlay, screen_rect)

    def _update_afterimages(
        self, groups: SpriteGroups, dt: float
    ) -> list[tuple[pygame.Surface, pygame.Rect]]:
        """Maintain the dash ghost trail (render-only, capped + fading).

        Each ghost keeps the world rectangle it was spawned over, and its
        screen position is mapped through the camera again every frame. It
        used to store the screen rect computed once, at spawn: the ghost then
        stayed nailed to the window while the world scrolled underneath it,
        so during a dash -- the one time the camera moves far enough per tick
        to see -- the trail slid backwards across the screen instead of hanging
        in the world, and a ghost spawned near an edge could sit against that
        edge for its whole life.
        """
        live: list[tuple[pygame.Surface, pygame.FRect, float]] = []
        for surface, world_rect, ttl in self._ghosts:
            ttl -= dt
            if ttl > 0.0:
                surface.set_alpha(int(255 * ttl / Afterimage.TTL))
                live.append((surface, world_rect, ttl))
        self._ghosts = live
        if dt > 0.0:
            self._ghost_timer += dt
            if self._ghost_timer >= Afterimage.SPAWN_EVERY:
                self._ghost_timer = 0.0
                self._spawn_afterimage(groups)
        return [
            (surface, surface.get_rect(center=self._ghost_center(world_rect)))
            for surface, world_rect, _ in self._ghosts
        ]

    def _ghost_center(self, world_rect: pygame.FRect) -> tuple[float, float]:
        """Where a ghost anchored to ``world_rect`` lands on screen this frame.

        The stretched surface was already sized at spawn, so only the centre
        has to be mapped: reusing the camera transform keeps the zoom and the
        shake identical to every other sprite, and costs no rescale per frame.
        """
        return self.camera.apply_covering(world_rect).center

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
            # image, so a world-sized ghost would stay small on screen. The
            # stretch is applied once here, at spawn; only the centre is mapped
            # per frame afterwards, so the trail costs no rescale per tick.
            ghost = self._scaled_image_once(ghost)
            ghost = dash_frame(ghost, self.camera.apply_covering(sprite.rect), apply_tint=False)[0]
            # The world rect is copied because the player's own rect is mutated
            # in place every tick, which would drag the ghost along with it.
            self._ghosts.append((ghost, pygame.FRect(sprite.rect), Afterimage.TTL))
            self._ghosts = self._ghosts[-Afterimage.MAX :]

    def _draw_ghosts(
        self,
        ghost_draws: list[tuple[pygame.Surface, pygame.Rect]],
        area: pygame.Rect | None = None,
    ) -> None:
        for surface, screen_rect in ghost_draws:
            if area is None or area.colliderect(screen_rect):
                self.display_surface.blit(surface, screen_rect)

    def _draw_full(
        self, groups: SpriteGroups, blits: list[tuple[pygame.Surface, pygame.Rect]]
    ) -> None:
        """Full-screen repaint (debug mode or fallback)."""
        self.display_surface.fill(self.background_color)
        for surface, screen_rect in blits:
            self.display_surface.blit(surface, screen_rect)

    def draw_health_bars(self, entities: Iterable[pygame.sprite.Sprite]) -> list[pygame.Rect]:
        """Draw the HP bars; return the rects they occupy, to be presented.

        The bars are anchored to the rects this frame blitted, not to the
        simulation position: the world pass interpolates between ticks, so a
        bar drawn at the simulation position sits half a tick behind its own
        sprite, which reads as a stripe of stale pixels trailing a moving
        enemy.
        """
        return self.ui_manager.draw_health_bars(entities, self.camera)

    def draw_debug_panels(
        self,
        player: Any,
        fps: float,
        sprite_count: int,
        combat_count: int,
        entity_count: int,
        collision_count: int,
        hit_stop: float,
        spawn_cooldown: float,
        game: Any = None,
        frame_time: float = 0.0,
        cache_size: int | None = None,
    ) -> None:
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
