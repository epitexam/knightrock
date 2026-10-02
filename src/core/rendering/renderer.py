from collections import deque
from collections.abc import Callable, Iterable
from itertools import chain
from time import perf_counter
from typing import Any, cast

import pygame

from src.core.colors import BG_COLORS, Color, Colors, FXColors
from src.core.level.level_data import LevelConfig
from src.core.rendering.camera import Camera
from src.core.rendering.overlay import NullOverlay, WorldOverlay
from src.core.rendering.tile_chunk_index import TileChunkIndex
from src.core.settings import Afterimage, HitFlash, ParryFlash, Turn
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
        stretched.fill(FXColors.speed_tint, special_flags=pygame.BLEND_RGB_ADD)
    return stretched, stretched.get_rect(center=screen_rect.center)


def turn_offset_px(sprite: object) -> float:
    """The trailing draw offset a pivoting fighter gets, in pixels.

    Read off ``turn_ratio``, which :class:`PlayerTurnState` publishes and
    clears: the ratio is the hold's own countdown, so the offset reaches zero
    on the same tick the facing lands and the flip has nothing left to correct.

    Signed against **the held facing**, which is the direction the fighter is
    travelling *away* from and so the one its feet are already going. Reading it
    off the live ``velocity.x`` instead looks equivalent and is not: the pivot
    is precisely the window in which that velocity crosses zero, so the sign
    would flip mid-hold and the sprite would jump the width of the effect in a
    single frame at the crossing. The held facing does not move for the whole
    hold -- the tag is what holds it, and it changes on the same tick the ratio
    goes to zero -- so this is stable exactly as long as it is drawn.

    Trailing rather than leading for the same reason: the sprite still shows
    the old face, so an offset towards where it is going would slide it off the
    mark in the direction its own feet are already travelling, which is the one
    direction the eye is not reading.
    """
    ratio = float(getattr(sprite, "turn_ratio", 0.0) or 0.0)
    if ratio <= 0.0:
        return 0.0
    travel = -1.0 if bool(getattr(sprite, "facing_right", True)) else 1.0
    lead = float(getattr(sprite, "turn_lead_px", Turn.LEAD_PX) or 0.0)
    return travel * lead * ratio


def turn_skew_px(sprite: object) -> float:
    """The lean a pivoting fighter gets, in pixels at the top of the sprite.

    Signed like :func:`turn_offset_px`, and for the same stability reason, so
    the figure is dragged as one piece: the body goes over *and* the top of it
    leads further than the feet do.
    """
    ratio = float(getattr(sprite, "turn_ratio", 0.0) or 0.0)
    if ratio <= 0.0:
        return 0.0
    travel = -1.0 if bool(getattr(sprite, "facing_right", True)) else 1.0
    skew = float(getattr(sprite, "turn_skew_px", Turn.SKEW_PX) or 0.0)
    return travel * skew * ratio


def turn_frame(
    image: pygame.Surface,
    screen_rect: pygame.Rect,
    offset_px: float,
    skew_px: float = 0.0,
) -> tuple[pygame.Surface, pygame.Rect]:
    """Slide and lean a pivot frame, keeping its height and its feet in place.

    Two effects, because one was not enough. The offset slides the whole body
    sideways; the skew leans it. A lean is a shear -- each row shifted in
    proportion to how high it is -- so the feet stay exactly where they were
    and only the top of the sprite goes over. A pivot is a fighter pivoting on
    planted feet, and a plain horizontal slide has no way to say that: a slide
    reads as the sprite being misplaced, a lean reads as the body being thrown.

    The rect is rebuilt from the sheared surface rather than merely moved. The
    shear returns something ``abs(skew)`` wider, and ``blit`` crops to the
    rect, so a rect left at the source width would eat the feet -- the one part
    of the fighter that has to stay put.
    """
    offset = int(round(offset_px))
    skew = _quantize_skew(int(round(skew_px)))
    if skew == 0:
        return image, screen_rect.move(offset, 0)

    sheared = _sheared(image, skew)
    moved = screen_rect.move(offset + min(0, skew), 0)
    moved.width = sheared.get_width()
    moved.height = sheared.get_height()
    return sheared, moved


#: ``(id(source), skew) -> sheared``, so a pivot shears each frame once per
#: distinct lean rather than once per draw. Sized off the sources in play: a
#: fighter pivoting touches a handful of animation frames per hold.
_SHEAR_CACHE: dict[tuple[int, int], pygame.Surface] = {}
_SHEAR_CACHE_MAX = 64


#: The lean is rounded to a multiple of this many pixels before shearing.
#:
#: Not a feel knob -- it belongs here rather than in ``settings.Turn`` because
#: it is a rendering-resolution decision, not a game-feel one. The shear is
#: rebuilt per distinct value and cached, and the lean is driven by a ratio
#: that changes every frame, so every frame wants its own integer lean: 21
#: distinct keys per animation frame. Two or three frames of the run sheet in
#: play at once is enough to blow past the cache cap, and then the cache purges,
#: rebuilds, purges again -- measured at 100% rebuild rate and 95 microseconds
#: a frame, forever, instead of a cache that would otherwise sit at zero.
#:
#: Halving the key space puts three frames of animation comfortably inside the
#: cap, and costs nothing visible: the lean was already rounded to whole pixels,
#: and a two-pixel step is about two degrees a frame on a 56-pixel sprite --
#: the same ramp, sampled less finely.
SKEW_STEP = 2


def _quantize_skew(skew: int) -> int:
    """``skew`` snapped to a multiple of :data:`SKEW_STEP`, away from zero.

    Two rules, and the second is the one that took a test to find.

    The snap never lands on zero for a non-zero input: a lean rounded down to
    nothing is not a smaller lean, it is no lean, and it would look like the
    quantisation had been honoured while quietly deleting the smallest tilts.
    ``round`` alone does exactly that -- Python rounds halves to even, so
    ``round(1 / 2)`` is ``0`` -- hence the ``max(1, ...)``.

    Rounding out from zero rather than to it also means a half-step goes the
    same way as a full one, so the ramp has no sawtooth at the bottom.
    """
    if skew == 0:
        return 0
    step = max(1, SKEW_STEP)
    snapped = max(1, int(round(abs(skew) / step))) * step
    return snapped if skew > 0 else -snapped


def _sheared(image: pygame.Surface, skew: int) -> pygame.Surface:
    """``image`` sheared sideways by ``skew`` pixels from bottom to top.

    The bottom row is the fixed one and the top row moves by ``skew``, so the
    feet stay on the floor and only the body goes over. Every row is placed at
    its own shear plus a common base of ``-min(0, skew)``, and the base is
    what keeps the result inside its own surface: with a leftward lean the rows
    run from x=0 at the top to x=-skew at the feet, so without it the feet
    would be blitted off the left edge and the shear would quietly become a
    half-applied one.

    Rounded to whole pixels, because a sub-pixel shear is a resample on every
    frame and this runs on the one fighter that is pivoting.
    """
    key = (id(image), skew)
    cached = _SHEAR_CACHE.get(key)
    if cached is not None:
        return cached

    width, height = image.get_size()
    base = -min(0, skew)
    out = pygame.Surface((width + abs(skew), height), pygame.SRCALPHA)
    out.fill((0, 0, 0, 0))

    last = max(1, height - 1)
    for y in range(height):
        # 0 at the bottom row, 1 at the top.
        depth = 1.0 - (y / last)
        row = image.subsurface(pygame.Rect(0, y, width, 1))
        out.blit(row, (base + int(round(skew * depth)), y))

    if len(_SHEAR_CACHE) >= _SHEAR_CACHE_MAX:
        _evict_half_shear_cache()
    _SHEAR_CACHE[key] = out
    return out


def _evict_half_shear_cache() -> None:
    """Drop the oldest half of the shear cache rather than all of it.

    Wiping the lot is what a cache full of entries you are still using does to
    itself: the next frame rebuilds them, and the frame after finds the cache
    full again. Measured with eight animation frames in play -- each rebuild
    sweeping the whole table -- that was a 100% rebuild rate at 95 microseconds
    a frame, sustained, in exchange for saving about a megabyte.

    Dropping half and letting it refill means an oversized working set costs
    some rebuilds rather than all of them. Insertion order is the eviction
    order here, which is not a real LRU: with a handful of fighters and a
    skew that walks down then back up, what is oldest is nearly always what is
    needed least, and the alternative -- ordering on last use -- means a write
    on every hit, which is the thing being optimised.
    """
    for stale in list(_SHEAR_CACHE)[: len(_SHEAR_CACHE) // 2]:
        del _SHEAR_CACHE[stale]


def _monochrome(image: pygame.Surface, tint: Color) -> pygame.Surface:
    """``image`` with its hue knocked back to one, keeping its shading.

    A manga speed line is a monochrome copy of the character: still the
    character, still lit from the same side, in one tone. So this keeps the
    luminance and drops the chroma, rather than filling the shape flat -- a
    flat fill also throws away the outline and the shading, and a row of
    those is a row of blobs.

    ``tint`` is multiplied over the result, so a near-white one cools the
    greyscale without darkening it much, and the ghost sits in the same
    family as the cyan the dashing sprite is lit with.
    """
    ghost = pygame.transform.grayscale(image.copy())
    ghost.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
    return ghost


def _ghost_alpha(ttl: float) -> int:
    """The opacity a ghost of this remaining life is stamped at.

    A ladder, not a slope: each level holds for an equal share of the ghost's
    life, so a dashing player leaves a few flat plates rather than a blur.
    """
    levels = Afterimage.LEVELS
    share = Afterimage.TTL / len(levels)
    remaining = min(len(levels) - 1, int(max(0.0, ttl) / share))
    return levels[len(levels) - 1 - remaining]


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
        # Flash silhouettes, keyed by ``(id(image), tint)`` like
        # ``_scaled_cache`` and holding the source for the same reason.
        self._flash_cache: dict[tuple[int, Color], tuple[pygame.Surface, pygame.Surface]] = {}
        self._dashing_player: object | None = None
        self._turning_player: object | None = None
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

    def _silhouette(self, image: pygame.Surface, color: Color) -> pygame.Surface:
        """A copy of ``image`` in ``color``, keeping its alpha, memoised per image.

        Building a mask and converting it to a surface costs 6.8us, and a
        flashing entity redraws for the whole 0.1s of its flash, so this was
        the most expensive per-sprite operation on the hit-feedback path. The
        silhouette only depends on the source image and the tint, never on the
        flash intensity, so it is built once and the caller copies it to set
        its own alpha.

        The source is kept in the cached value: an ``id``-keyed dict can be
        handed a freed surface whose id was recycled, which would return a
        silhouette of the wrong size.
        """
        key = (id(image), color)
        cached = self._flash_cache.get(key)
        if cached is not None:
            return cached[1]
        mask = pygame.mask.from_surface(image)
        silhouette = mask.to_surface(setcolor=(*color, 255), unsetcolor=(0, 0, 0, 0))
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
        self._turning_player = self._find_turning_player(groups)
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

    def _find_turning_player(self, groups: SpriteGroups) -> pygame.sprite.Sprite | None:
        """The one sprite mid-pivot, or None.

        The same shape and the same reason as :meth:`_find_dashing_player`:
        ``turn_ratio`` is one attribute lookup on the entity, asked once here
        instead of of every visible sprite in the blit loop.
        """
        for sprite in groups.entity_sprites:
            if float(getattr(sprite, "turn_ratio", 0.0) or 0.0) > 0.0:
                return cast("pygame.sprite.Sprite", sprite)
        return None

    def _collect_visible_blits(
        self, groups: SpriteGroups
    ) -> list[tuple[pygame.Surface, pygame.Rect]]:
        """Camera-cull and compute target rects for every visible plane.

        One flat loop over the three sprite draw planes, in paint order: the
        frozen tile plane (through its chunk index, when one is installed), the
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

        They are split by a particle's own ``behind`` flag: ground-level marks
        go in under the moving plane, so a fighter is never painted over by
        the dust they kicked up, and everything else stays on top where a
        spark can be seen.
        """
        blits: list[tuple[pygame.Surface, pygame.Rect]] = []
        static_index = self._static_index
        foreground_index = self._foreground_index
        # Resolved once: ``begin_frame`` is idempotent within a frame, and
        # ``colliderect`` is the same intersection ``Camera.is_visible`` makes.
        viewport = self.camera.viewport
        colliderect = viewport.colliderect
        behind_fx, front_fx = self._collect_fx_blits(groups, colliderect)

        for sprite in self._static_plane(groups, static_index, viewport):
            self._append_cached_blit(blits, sprite, colliderect)
        blits.extend(behind_fx)
        for sprite in self._sprite_planes(groups, foreground_index, viewport):
            self._append_cached_blit(blits, sprite, colliderect)
        blits.extend(front_fx)
        return blits

    def _collect_fx_blits(
        self, groups: SpriteGroups, colliderect: Callable[[pygame.FRect | pygame.Rect], bool]
    ) -> tuple[list[tuple[pygame.Surface, pygame.Rect]], list[tuple[pygame.Surface, pygame.Rect]]]:
        """The FX plane, split into the marks that go under the world and the rest."""
        behind: list[tuple[pygame.Surface, pygame.Rect]] = []
        front: list[tuple[pygame.Surface, pygame.Rect]] = []
        for sprite in groups.fx_sprites:
            rect = sprite.rect
            image_source = sprite.image
            if rect is None or image_source is None or not colliderect(rect):
                continue
            target = behind if getattr(sprite, "behind", False) else front
            target.append((self._scaled_image_once(image_source), self.camera.apply_snapped(rect)))
        return behind, front

    def _static_plane(
        self,
        groups: SpriteGroups,
        static_index: TileChunkIndex | None,
        viewport: pygame.FRect,
    ) -> Iterable[pygame.sprite.Sprite]:
        """The frozen tile plane, through its chunk index when there is one."""
        if static_index is None:
            return ()
        return static_index.candidates(viewport)

    def _sprite_planes(
        self,
        groups: SpriteGroups,
        foreground_index: TileChunkIndex | None,
        viewport: pygame.FRect,
    ) -> Iterable[pygame.sprite.Sprite]:
        """The moving plane and the foreground decor, in paint order.

        A ``chain`` rather than a concatenation because the moving plane is a
        live group: a list would snapshot it, and a sprite added between the
        planes being walked and the blit loop running would be drawn at a
        position that does not match the frame it belongs to.
        """
        foreground = (
            groups.fg_sprites if foreground_index is None else foreground_index.candidates(viewport)
        )
        return chain(groups.all_sprites, foreground)

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
        if self._turning_player is not None and sprite is self._turning_player:
            image, screen_rect = turn_frame(
                image, screen_rect, turn_offset_px(sprite), turn_skew_px(sprite)
            )
        blits.append((image, screen_rect))

    def _collect_flashes(self, groups: SpriteGroups) -> list[tuple[pygame.Surface, pygame.Rect]]:
        """Tint overlays for entities that just took a hit or just parried.

        Only entities carry the timers, so this walks ``entity_sprites``:
        scanning ``all_sprites`` cost a ``getattr`` on every tile of the level,
        ~1000 of them, to find at most a handful of flashes.

        The parry wash is the same overlay in gold, and it is the whole
        difference between a block and a perfect one on the character itself:
        the reaction animation is already shared, so a parry that also threw
        its own burst and washed the whole frame was three times the screen
        coverage of the thing it is a bigger version of.
        """
        flashes: list[tuple[pygame.Surface, pygame.Rect]] = []
        for sprite in groups.entity_sprites:
            hurt = float(getattr(sprite, "flash_timer", 0.0) or 0.0)
            parried = float(getattr(sprite, "parry_flash_timer", 0.0) or 0.0)
            if hurt <= 0.0 and parried <= 0.0:
                continue
            if not self.camera.is_visible(sprite.rect):
                continue
            color = Colors.white
            strength = hurt / HitFlash.DURATION if hurt > 0.0 else 0.0
            if parried > 0.0:
                color = Colors.gold
                strength = max(strength, ParryFlash.ALPHA * min(1.0, parried / ParryFlash.DURATION))
            overlay = self._silhouette(sprite.image, color).copy()
            overlay.set_alpha(int(255 * min(1.0, strength)))
            screen_rect = self.camera.apply_snapped(sprite.rect)
            overlay = self._scaled_image_once(overlay)
            if is_player_dashing(sprite):
                overlay, screen_rect = dash_frame(overlay, screen_rect)
            # The same slide and lean the body got, or a flash fired mid-pivot
            # paints a silhouette of a fighter who is not standing there.
            overlay, screen_rect = turn_frame(
                overlay, screen_rect, turn_offset_px(sprite), turn_skew_px(sprite)
            )
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
                surface.set_alpha(_ghost_alpha(ttl))
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
            # Zoomed for the camera, and deliberately *not* run through
            # ``dash_frame``. The stretch is what the live sprite is doing --
            # it is a cue for the movement, read while it happens. Stamping a
            # frozen copy of it turns every afterimage into a lozenge at
            # 1.6 wide and 0.6 tall, and six of those in a row is a row of
            # pancakes rather than a trail of the fighter. A manga afterimage
            # is the character's own shape; the shape is what the player
            # recognises, so that is what gets copied.
            ghost = self._scaled_image_once(_monochrome(sprite.image, FXColors.speed_ghost))
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
        would reach them. The whole chain still returns them because
        ``world_overlay_bars`` computes them anyway, and dropping the return
        would mean changing a port signature to save nothing. Be aware that
        ``Level.draw`` discards the result: the only readers today are the
        tests that assert which rects were painted.
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
