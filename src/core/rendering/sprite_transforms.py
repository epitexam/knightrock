"""Dash/turn sprite transforms and the shear cache behind them.

These are render-only transforms: they stretch, slide and shear a surface for
the frame being drawn and never touch simulation state. They are imported back
into :mod:`src.core.rendering.renderer` so existing call sites and tests keep
their historical paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.core.colors import FXColors
from src.states import state_names

if TYPE_CHECKING:
    from src.entities.entity import Entity


DASH_STRETCH_X = 1.6
"""Horizontal cartoon stretch applied to dashing players (render-only)."""

DASH_STRETCH_Y = 0.6
"""Vertical squash paired with the dash stretch (render-only)."""


def is_player_dashing(sprite: Entity) -> bool:
    """Whether the entity is a player currently in its dash state."""
    return (
        sprite.faction == "player" and sprite.state_machine.current_state_name == state_names.DASH
    )


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


def turn_offset_px(sprite: Entity) -> float:
    """The trailing draw offset a pivoting fighter gets, in pixels.

    Read off ``render_hints.turn_ratio``, which :class:`PlayerTurnState` publishes and
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
    ratio = sprite.render_hints.turn_ratio
    if ratio <= 0.0:
        return 0.0
    travel = -1.0 if sprite.facing_right else 1.0
    return travel * sprite.turn_lead_px * ratio


def turn_skew_px(sprite: Entity) -> float:
    """The lean a pivoting fighter gets, in pixels at the top of the sprite.

    Signed like :func:`turn_offset_px`, and for the same stability reason, so
    the figure is dragged as one piece: the body goes over *and* the top of it
    leads further than the feet do.
    """
    ratio = sprite.render_hints.turn_ratio
    if ratio <= 0.0:
        return 0.0
    travel = -1.0 if sprite.facing_right else 1.0
    return travel * sprite.turn_skew_px * ratio


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


#: ``(id(source), skew) -> (source, sheared)``, so a pivot shears each frame
#: once per distinct lean rather than once per draw. Sized off the sources in
#: play: a fighter pivoting touches a handful of animation frames per hold.
#: The source is kept in the value for the same reason the scaled and flash
#: caches keep theirs: a key built from ``id`` alone can be hit by a freed
#: surface whose id was recycled, which would hand back a stale, wrongly sized
#: blit.
_SHEAR_CACHE: dict[tuple[int, int], tuple[pygame.Surface, pygame.Surface]] = {}
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
    if cached is not None and cached[0] is image:
        return cached[1]

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
        _evict_half(_SHEAR_CACHE)
    _SHEAR_CACHE[key] = (image, out)
    return out


#: Working set, not a budget. The shipped level draws 38 distinct images
#: through the scale cache at one density; a bound set to that number rebuilds
#: the cache every frame, which is what made the shear cache's own first bound
#: cost 95us a frame. Four times the measured set gives room for the debug
#: spawn bench, which is the caller that keeps churning new Surfaces -- and at
#: roughly 8 Ko a retained blend, 512 entries is a few megabytes of worst case
#: instead of the unbounded growth the caches had, where every spawned enemy
#: left one behind for the rest of the session.
SCALE_CACHE_MAX = 512
FLASH_CACHE_MAX = 512


def _evict_half(cache: dict) -> None:
    """Drop the oldest half of a cache rather than all of it.

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
    for stale in list(cache)[: len(cache) // 2]:
        del cache[stale]



def clear_shear_cache() -> None:
    """Drop sheared surfaces derived from an obsolete display format."""
    _SHEAR_CACHE.clear()
