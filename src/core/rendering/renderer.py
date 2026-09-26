from collections import deque
from collections.abc import Iterable
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
    """Draws the world into the render target.

    Every frame is a complete repaint of the target: erase, blit, done. It used
    to return the rects that changed so the loop could present only those, which
    bought a partial update and cost a bookkeeping machine that had to stay
    exactly in step with the drawing -- the erase region, the declared overlay
    rects, and the previous frame's rects all had to agree or stale pixels
    survived. With a fixed render target there is nothing left to present
    partially, so the whole class of bug is gone rather than fixed.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        camera: Camera,
        config: LevelConfig | None = None,
    ) -> None:
        self.surface = surface
        self.camera = camera
        self.ui_manager = UIManager(surface)
        self.background_color = self._resolve_background_color(config)
        self._ghosts: list[tuple[pygame.Surface, pygame.FRect, float]] = []
        self._ghost_timer: float = 0.0
        # Scaled sprite surfaces: ``id(image) -> (image, scaled)``. Scaling a
        # surface every frame for every visible sprite is expensive, so each
        # image is scaled once and reused; the key used to carry the camera zoom
        # too, and no longer does, because the zoom is gone.
        # The source is kept *in the cached value* on purpose: a dict key built
        # from ``id(image)`` alone can be hit by a freed surface whose id was
        # recycled, which would hand back a stale, wrongly sized blit.
        self._scaled_cache: dict[int, tuple[pygame.Surface, pygame.Surface]] = {}
        # White damage-flash silhouettes, keyed by ``id(image)`` like
        # ``_scaled_cache`` and holding the source for the same reason.
        self._flash_cache: dict[int, tuple[pygame.Surface, pygame.Surface]] = {}
        self._dashing_player: object | None = None
        self._debug_samples: dict[str, deque[float]] = {
            "world_ui_ms": deque(maxlen=120),
            "panels_ms": deque(maxlen=120),
        }

    def set_surface(self, surface: pygame.Surface) -> None:
        """Adopt a new render target, after the render scale changed.

        Nothing else reaches the renderer. A window resize does not come here:
        the target is the same surface either way, only the way it is presented
        changes, and that is ``Presentation``'s business.
        """
        self.surface = surface
        self.ui_manager.set_surface(surface)
        self._scaled_cache.clear()
        self._flash_cache.clear()

    @property
    def _render_scale(self) -> float:
        """Target pixels per world unit, read off the two sizes we are given.

        Derived rather than passed so the renderer cannot be handed a scale that
        disagrees with the surface it is drawing into.
        """
        world_width = self.camera.framing.width
        if world_width <= 0:
            return 1.0
        return self.surface.get_width() / world_width

    def _scaled_image(self, image: pygame.Surface) -> pygame.Surface:
        """Scale ``image`` to the render scale, caching the result.

        Returns the image untouched at scale 1 so a 1x build never pays for
        scaling.
        """
        scale = self._render_scale
        if scale == 1.0:
            return image
        key = id(image)
        cached = self._scaled_cache.get(key)
        if cached is not None:
            return cached[1]
        scaled = self._rescale(image, scale)
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
        """Scale a transient surface to the render scale, without caching it.

        Afterimages and damage flashes build a brand new surface every frame,
        so caching them by ``id()`` would grow the cache forever. They are
        short-lived by nature, so scaling them directly is both correct and
        cheap enough.
        """
        scale = self._render_scale
        if scale == 1.0:
            return image
        return self._rescale(image, scale)

    @staticmethod
    def _rescale(image: pygame.Surface, scale: float) -> pygame.Surface:
        """Scale a surface by ``scale``, smoothing only when enlarging.

        Enlarging an already-integral factor is the case that matters, since
        the render scale is an integer: the nearest-neighbour path then
        reproduces every source pixel exactly. Shrinking is also nearest, where
        smoothing would only soften a sprite that is on its way out.
        """
        width = max(1, round(image.get_width() * scale))
        height = max(1, round(image.get_height() * scale))
        if scale > 1.0:
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

    def draw(
        self,
        groups: SpriteGroups,
        debug_enabled: bool = False,
        dt: float = 0.0,
        alpha: float = 0.0,
    ) -> None:
        """Draw one complete frame of the world into the render target.

        ``alpha`` is the position within the current simulation tick, in
        [0, 1]. It is passed rather than read from the clock so the blend is
        a pure function of the loop state and stays reproducible. The camera
        applies it, so every sprite, the HP bars and the debug overlay read
        one transform and cannot drift apart.

        Returns nothing. It used to return the rects that changed so the loop
        could present only those, and the HUD and the health bars -- painted
        after this pass decides what to present -- had to be declared one
        frame ahead for the next frame's erase to reach them. A gauge that
        shrank left a stripe behind whenever that bookkeeping slipped. A full
        repaint has no such window.
        """
        self.camera.begin_frame(alpha)
        self._dashing_player = self._find_dashing_player(groups)
        self.surface.fill(self.background_color)
        blits = self._collect_visible_blits(groups)
        for surface, screen_rect in blits:
            self.surface.blit(surface, screen_rect)
        self._draw_ghosts(self._update_afterimages(groups, dt))
        self._draw_flashes(self._collect_flashes(groups))
        if debug_enabled:
            started = perf_counter()
            self.ui_manager.draw_debug_overlays(groups.all_sprites, self.camera, dt)
            self._record_debug_sample("world_ui_ms", (perf_counter() - started) * 1000.0)

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

    def _collect_visible_blits(
        self, groups: SpriteGroups
    ) -> list[tuple[pygame.Surface, pygame.Rect]]:
        """Camera-cull and compute target rects for every visible plane.

        The FX plane is deliberately *not* scaled through ``_scaled_image``:
        FX particles rebuild their ``image`` every tick, so each one is a new
        Surface object and each one would add a permanent entry to the scale
        cache. Caching them grew the cache by one retained surface per FX
        sprite per tick, for the whole session, with no eviction. They are
        short-lived by nature, so they go through ``_scaled_image_once``.
        """
        blits: list[tuple[pygame.Surface, pygame.Rect]] = []
        cached_planes = (*groups.all_sprites, *groups.fg_sprites)
        for sprite in cached_planes:
            if self.camera.is_visible(sprite.rect):
                screen_rect = self._screen_rect(sprite)
                image = self._scaled_image(sprite.image)
                # Only a player can be dashing, and a player is an entity, so
                # this branch is resolved by identity rather than by a
                # ``getattr`` walk over every tile of the level.
                if self._dashing_player is not None and sprite is self._dashing_player:
                    image, screen_rect = dash_frame(image, screen_rect)
                blits.append((image, screen_rect))
        for sprite in groups.fx_sprites:
            if self.camera.is_visible(sprite.rect):
                blits.append(
                    (
                        self._scaled_image_once(sprite.image),
                        self.camera.apply_covering(sprite.rect),
                    )
                )
        return blits

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

    def _draw_flashes(self, flashes: list[tuple[pygame.Surface, pygame.Rect]]) -> None:
        for overlay, screen_rect in flashes:
            self.surface.blit(overlay, screen_rect)

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

    def _draw_ghosts(self, ghost_draws: list[tuple[pygame.Surface, pygame.Rect]]) -> None:
        for surface, screen_rect in ghost_draws:
            self.surface.blit(surface, screen_rect)

    def draw_health_bars(self, entities: Iterable[pygame.sprite.Sprite]) -> list[pygame.Rect]:
        """Draw the HP bars over the world pass; return the rects they occupy.

        The bars are anchored to the rects this frame blitted, not to the
        simulation position: the world pass interpolates between ticks, so a
        bar drawn at the simulation position sits half a tick behind its own
        sprite, which reads as a stripe trailing a moving enemy.

        The rects used to be handed to the presenter so the next frame's erase
        would reach them. Nothing needs that any more, but ``world_ui`` already
        computes them, so they are returned rather than recomputed by a caller
        that wants to reason about what was painted.
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
        surface = self.ui_manager.renderer.surface
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
