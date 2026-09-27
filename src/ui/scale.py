"""The interface's size, and the one rule about it.

The scale the views are handed is **the player's preference times the target's
pixel density**. Both halves are needed and neither is optional:

- the density is what keeps the interface the same apparent size on a 4K panel
  and on a 1366x768 laptop, since the render target is now the window and the
  window can be anything;
- the preference is the player's own lever, and it is the only one: nothing in
  the game decides that 0.8 is too small to read.

So the scale is a continuous number, and the three views that used to each
refuse anything but ``(0.8, 1.0, 1.2)`` now share the check here. Three copies
of the same three-value ladder is three places to forget, and the density makes
the ladder impossible anyway: at a density of 1.889 the scale is 1.511, which
the old check rejected on sight.
"""

#: Outside this, the interface is either invisible or larger than any display.
MIN_UI_SCALE = 0.25
MAX_UI_SCALE = 8.0


def checked_ui_scale(scale: float) -> float:
    """The interface scale, or refused.

    Bounded rather than a fixed set, because the number is a product and a
    product of two legitimate values is not one of the values. A density of 8
    (a 9216x5184 window) times a preference of 1.0 is a scale the views have to
    survive, and a NaN would silently produce zero-sized rects everywhere.
    """
    if scale != scale or not MIN_UI_SCALE <= scale <= MAX_UI_SCALE:
        raise ValueError(
            f"The interface scale must be between {MIN_UI_SCALE} and {MAX_UI_SCALE}, got {scale!r}"
        )
    return scale


def font_size(base: int, scale: float) -> int:
    """A font size in whole pixels.

    The one place a scale becomes a font size, so that a view's cache keyed on
    the size it asked for is keyed on exactly what it will get: at a fractional
    scale two neighbouring values can round to the same size, and a cache keyed
    on the scale itself would then hold two identical sets of fonts.
    """
    return max(1, round(base * scale))


#: How far a *screen* overlay may grow with the window. A debug panel is screen
#: furniture, not an annotation of the world, so it has a ceiling: at 4K the
#: density is 3.3 and a panel scaled by it would cover a quarter of the display
#: to say the same thing three times larger.
PANEL_MAX_SCALE = 2.0


def world_scale(density: float) -> float:
    """The scale of an overlay that annotates the **world**.

    Hitboxes, velocities and the label cards pinned above a sprite are
    descriptions of that world, so they scale with it: a one-art-pixel outline
    has to stay one art pixel wide, or it reads as a hairline over a tileset
    drawn twice as large. Measured at a density of 1.889, an unscaled outline
    lands at 53% of its intended weight and is invisible in practice -- which is
    what "F1 does nothing" turned out to be.
    """
    return max(1.0, density)


def screen_scale(density: float) -> float:
    """The scale of an overlay that annotates the **screen**.

    Bounded at both ends: never smaller than the design size, and never more
    than :data:`PANEL_MAX_SCALE` so a 4K window gets readable panels rather than
    enormous ones.
    """
    return min(max(1.0, density), PANEL_MAX_SCALE)


#: How many quantised font sizes a view keeps. A window drag walks through
#: hundreds of densities; each distinct pixel size is three ``SysFont`` calls, so
#: the cache is emptied rather than grown when it gets unreasonable. The cost of
#: getting it wrong is a font scan per frame, which is what the cache is for.
FONT_CACHE_ENTRIES = 16
