from collections import deque
from collections.abc import Callable, Iterable
from itertools import chain
from time import perf_counter
from typing import Any, cast

import pygame

from src.core.colors import BG_COLORS, Color, Colors
from src.core.level.level_data import LevelConfig
from src.core.rendering.camera import Camera
from src.core.rendering.overlay import NullOverlay, WorldOverlay
from src.core.rendering.tile_chunk_index import TileChunkIndex
from src.core.settings import Afterimage, HitFlash
from src.core.sprite_groups import SpriteGroups

DASH_STRETCH_X = 1.6
"""Horizontal cartoon stretch applied to dashing players (render-only)."""

DASH_STRETCH_Y = 0.6
"""Vertical squash paired with the dash stretch (render-only)."""


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
        overlay: WorldOverlay | None = None,
    ) -> None:
        self.surface = surface
        self.camera = camera
        #: The interface drawn over the world, injected rather than built.
        #: See :mod:`src.core.rendering.overlay` for why the arrow between
        #: ``core`` and ``ui`` points this way and not the other. Defaults to
        #: drawing nothing, which is what a renderer built to answer "is this
        #: tile culled" wants.
        self.overlay: WorldOverlay = overlay if overlay is not None else NullOverlay()
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
        #: Chunked culls over the frozen tile planes, or None when the world
        #: has none to index. Installed by the level after the world is built;
        #: a renderer that was handed a bare group (every test that draws a
        #: couple of sprites) keeps the linear scan, which is the same result
        #: for a plane small enough not to need an index.
        self._static_index: TileChunkIndex | None = None
        self._foreground_index: TileChunkIndex | None = None
        self._debug_samples: dict[str, deque[float]] = {
            "world_ui_ms": deque(maxlen=120),
            "panels_ms": deque(maxlen=120),
        }

    def set_static_planes(
        self, statics: TileChunkIndex | None, foreground: TileChunkIndex | None = None
    ) -> None:
        """Adopt chunked culls for the level's frozen tile planes.

        Both indexes are optional and independent: a level with no foreground
        layer passes nothing for it, and a renderer with neither keeps the
        linear scan, so nothing about the frame changes either way.
        """
        self._static_index = statics
        self._foreground_index = foreground

    def set_surface(self, surface: pygame.Surface) -> None:
        """Adopt a new render target, after the render scale changed.

        Nothing else reaches the renderer. A window resize does not come here:
        the target is the same surface either way, only the way it is presented
        changes, and that is ``Presentation``'s business.
        """
        self.surface = surface
        # The camera owns the scale, so it has to hear about the new target in
        # the same breath. Skipping this leaves the rectangles at the old scale
        # while the images move to the new one, which is the mismatch that draws
        # a world at the wrong size with no error anywhere.
        self.camera.set_target(surface)
        # The camera has just re-read the density, so the interface's two scales
        # are derived from it here rather than each keeping its own copy.
        self.overlay.set_surface(surface, self.camera.density)
        self._scaled_cache.clear()
        self._flash_cache.clear()

    @property
    def _density(self) -> float:
        """Target pixels per world unit, as the camera computed it.

        Not derived here as well. Two derivations of the same number is one too
        many, and this is the one that matters: the camera uses it for the
        rectangles, so a disagreement would scale the images and not the rects
        and the frame would show a world half the size it claims to.
        """
        return self.camera.density

    def _scaled_image(self, image: pygame.Surface) -> pygame.Surface:
        """Magnify ``image`` to the density, caching the result.

        Returns the image untouched at a density of exactly 1 so a target that
        needs no magnification never pays for one.
        """
        if self._density == 1.0:
            return image
        key = id(image)
        cached = self._scaled_cache.get(key)
        if cached is not None:
            return cached[1]
        scaled = self._rescale(image)
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
        """Magnify a transient surface to the density, without caching it.

        Afterimages and damage flashes build a brand new surface every frame,
        so caching them by ``id()`` would grow the cache forever. They are
        short-lived by nature, so scaling them directly is both correct and
        cheap enough.
        """
        if self._density == 1.0:
            return image
        return self._rescale(image)

    def _rescale(self, image: pygame.Surface) -> pygame.Surface:
        """Magnify a surface to the density, nearest neighbour.

        Nearest, and the size asked of the camera rather than computed here:
        the art is authored at one pixel per world unit, so a magnified sprite
        stays a block of whole source pixels instead of a smoothed
        approximation of one, and the destination rectangle the sprite is blitted
        into is built from the very same number -- which is what keeps
        ``pygame.blit`` from resampling it behind our back.
        """
        return pygame.transform.scale(image, self.camera.scaled_size(image.get_size()))

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
            overlays = perf_counter()
            self.overlay.draw_debug_overlays(groups.every_sprite, self.camera, dt)
            self._record_debug_sample("world_ui_ms", (perf_counter() - overlays) * 1000.0)

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

        One flat loop over the three draw planes, in paint order: the frozen
        tile plane (through its chunk index, when one is installed), the
        moving plane, then the foreground decor. With the index this is ~130
        sprites instead of the ~970 a single scan of the level cost, and the
        static sprites it skips are *not* walked at all -- which is why the
        tile layers live in their own group rather than in ``all_sprites``.

        The exact ``is_visible`` test still runs on every candidate. The index
        is deliberately a conservative superset, so it decides what is worth
        asking about and never what gets drawn; ``Camera.is_visible`` is
        inlined here as ``viewport.colliderect`` because at a few hundred calls
        per frame the extra Python frame is a measurable share of the loop.

        The FX plane is deliberately *not* scaled through ``_scaled_image``:
        FX particles rebuild their ``image`` every tick, so each one is a new
        Surface object and each one would add a permanent entry to the scale
        cache. Caching them grew the cache by one retained surface per FX
        sprite per tick, for the whole session, with no eviction. They are
        short-lived by nature, so they go through ``_scaled_image_once``.
        """
        blits: list[tuple[pygame.Surface, pygame.Rect]] = []
        static_index = self._static_index
        foreground_index = self._foreground_index
        # Resolved once: ``begin_frame`` is idempotent within a frame, and
        # ``colliderect`` is the same intersection ``Camera.is_visible`` makes.
        viewport = self.camera.viewport
        colliderect = viewport.colliderect
        for sprite in self._draw_planes(groups, static_index, foreground_index, viewport):
            self._append_cached_blit(blits, sprite, colliderect)

        for sprite in groups.fx_sprites:
            if colliderect(sprite.rect):
                blits.append(
                    (
                        self._scaled_image_once(sprite.image),
                        self.camera.apply_snapped(sprite.rect),
                    )
                )
        return blits

    def _draw_planes(
        self,
        groups: SpriteGroups,
        static_index: TileChunkIndex | None,
        foreground_index: TileChunkIndex | None,
        viewport: pygame.FRect,
    ) -> Iterable[pygame.sprite.Sprite]:
        """The three draw planes, in paint order, without materialising them.

        A ``chain`` rather than a concatenation because the moving plane is a
        live group: a list would snapshot it, and a sprite added between the
        planes being walked and the blit loop running would be drawn at a
        position that does not match the frame it belongs to.
        """
        if static_index is None:
            return chain(groups.all_sprites, groups.fg_sprites)
        foreground = (
            groups.fg_sprites if foreground_index is None else foreground_index.candidates(viewport)
        )
        return chain(static_index.candidates(viewport), groups.all_sprites, foreground)

    def _append_cached_blit(
        self,
        blits: list[tuple[pygame.Surface, pygame.Rect]],
        sprite: pygame.sprite.Sprite,
        colliderect: Callable[[pygame.FRect | pygame.Rect], bool],
    ) -> None:
        """Cull one sprite through the scale cache and queue its blit.

        A sprite with no rectangle or no image is skipped: ``pygame`` allows
        both to be unset, and the cull is asked about every sprite in a plane
        rather than only the ones a caller vouched for.
        """
        rect = sprite.rect
        image_source = sprite.image
        if rect is None or image_source is None or not colliderect(rect):
            return
        screen_rect = self.camera.apply_snapped(rect)
        image = self._scaled_image(image_source)
        # Only a player can be dashing, and a player is an entity, so this
        # branch is resolved by identity rather than by a ``getattr`` walk
        # over every tile of the level.
        if self._dashing_player is not None and sprite is self._dashing_player:
            image, screen_rect = dash_frame(image, screen_rect)
        blits.append((image, screen_rect))

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
            screen_rect = self.camera.apply_snapped(sprite.rect)
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
        has to be mapped: reusing the camera transform keeps the shake identical
        to every other sprite, and costs no rescale per frame.
        """
        return self.camera.apply_snapped(world_rect).center

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
            ghost = dash_frame(ghost, self.camera.apply_snapped(sprite.rect), apply_tint=False)[0]
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
        return self.overlay.draw_health_bars(entities, self.camera)

    def draw_debug_panels(self, **counters: Any) -> None:
        """Ask the overlay to draw the screen-side debug panels.

        Only the *when* lives here -- the renderer owns the frame, so it is the
        one that knows a frame is being presented and how long the panels took.
        The *what* is the overlay's, including the panel layout, which is why
        ``PanelLayout`` is no longer imported by ``core``.
        """
        started = perf_counter()
        self.overlay.draw_debug_panels(**counters, debug_stats=self.debug_metrics_snapshot())
        self._record_debug_sample("panels_ms", (perf_counter() - started) * 1000.0)
