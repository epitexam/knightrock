"""How much of a window the picture occupies, and how many pixels a world unit is.

The whole display system is three lines of arithmetic, and they live here so
that there is exactly one copy of each:

- a window of any shape is fitted to the framing's aspect (:func:`letterbox`);
- the resulting rectangle is the render target, so the finished frame is blitted
  onto the window **1:1** and no resampling of the picture ever happens;
- the density of pixels is read back off that rectangle (:func:`density_for`),
  which is the only definition of it in the codebase.

Why the target is the window
----------------------------
It used to be ``Framing x integer``, a fixed set of sizes, and the finished
frame was then scaled onto the window. That cannot be sharp on an arbitrary
display: the number of screen pixels a world unit occupies is
``window / framing`` whatever the integer was, so every configuration that is not
an exact multiple of the framing resamples the picture. Measured on the
registered level at 2176x1224: a 1152x648 target upscaled by 1.889 with
``smoothscale`` cost 4.24 ms per frame and turned a 13-colour tileset into 128
colours. Drawing into the window itself costs nothing at all and is exact.

The two numbers are not independent, and that is the point: the target *is* the
letterbox rectangle, so the density is whatever that rectangle implies. There is
no setting that can put them out of step.
"""

import pygame

from .framing import DEFAULT_FRAMING, Framing

#: How far the two axes' densities may disagree, expressed in pixels of target.
#:
#: Rounding a letterbox to whole pixels cannot preserve a ratio exactly, so a
#: target's two axes always imply densities that differ slightly. The bound is
#: "at most a pixel of mismatch across the whole frame": the framing's height in
#: pixels then misses the target's by no more than one, which is the rounding the
#: letterbox already made and cannot be seen. Beyond that the two axes are
#: describing different worlds, and the frame would be drawn anisotropically --
#: stretched on one axis only, which is the one thing a render target exists to
#: prevent.
DENSITY_TOLERANCE_PX = 1.0


def letterbox(
    window: tuple[int, int],
    framing: Framing = DEFAULT_FRAMING,
    *,
    pixel_perfect: bool = False,
) -> pygame.Rect:
    """The rectangle of ``window`` that carries the picture, centred.

    Fits the framing's aspect inside the window and centres what is left over.
    A window that already has the framing's aspect gets no bars at all, which is
    the common case and the reason this is a letterbox and not a fixed inset.

    ``pixel_perfect`` takes the largest **whole** multiple of the framing that
    still fits, so every art pixel becomes an exact k-by-k block. The bars grow
    to take the difference. On a window too small to hold even one whole
    multiple there is nothing to snap to, and clamping a multiple down to the
    window would be worse than useless: it would hand back a rectangle of the
    wrong aspect, and a target whose two axes imply different densities is
    refused. So that case gets the fitted rectangle, unchanged, and the caller's
    job is to say so rather than to fail.
    """
    width, height = window
    if width <= 0 or height <= 0:
        return pygame.Rect(0, 0, 1, 1)
    fit = min(width / framing.width, height / framing.height)
    if pixel_perfect and int(fit) >= 1:
        fit = float(int(fit))
    fitted = (
        max(1, min(width, round(framing.width * fit))),
        max(1, min(height, round(framing.height * fit))),
    )
    return pygame.Rect((width - fitted[0]) // 2, (height - fitted[1]) // 2, *fitted)


def fits_whole_pixel(window: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> bool:
    """Whether a whole multiple of the framing fits in ``window``.

    What the ``pixel_perfect`` row has to know before offering itself: on a
    window narrower than the framing there is no whole multiple to snap to, and
    the row has to say that instead of pretending.
    """
    if window[0] <= 0 or window[1] <= 0:
        return False
    return min(window[0] / framing.width, window[1] / framing.height) >= 1.0


def already_a_whole_multiple(window: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> bool:
    """Whether the window is *already* sized to a whole multiple of the framing.

    ``fits_whole_pixel`` asks whether a whole multiple fits; this asks whether the
    window already is one. They disagree on exactly one class of window, and it
    is the class that reads as a broken row: a window already sized to a whole
    multiple, where :func:`letterbox` returns the same rectangle with the flag on
    and off.

    There the setting is honoured and the picture is unchanged, which is correct
    -- there was nothing to snap to -- but the player pressing the row gets no
    picture at all, and a row that flips its label while the screen sits still is
    indistinguishable from a dead one.

    Rarer than the other case: only exact multiples of the framing, so a
    1152x648 or 2304x1296 window at the shipped framing, and a borderless desktop
    that happens to be exactly 2x.

    The ``fits_whole_pixel`` guard is not decoration, and it is what this function
    got wrong first. Without it, a window too small to hold a whole multiple
    also returns the same rectangle -- :func:`letterbox` hands the fitted one back
    unchanged -- so the comparison alone reports a window with no whole multiple
    in it as "already one". That is the other refusal, and the two have to stay
    distinguishable: a caller that checked this alone would tell a player with a
    window too small for the art that there is nothing left to do.
    """
    return (
        fits_whole_pixel(window, framing)
        and letterbox(window, framing).size == letterbox(window, framing, pixel_perfect=True).size
    )


def density_for(size: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> float:
    """Target pixels per world unit, read off a target of ``size``.

    A refusal, not a clamp: a target whose two axes imply different densities
    is not the framing at some density, it is a mistake somewhere upstream, and
    rounding it away is how a frame ends up drawn at a density nobody asked for
    while the framing contract still claims otherwise.
    """
    if size[0] <= 0 or size[1] <= 0:
        raise ValueError(f"A render target needs a positive size, got {size!r}")
    horizontal = size[0] / framing.width
    vertical = size[1] / framing.height
    slack = DENSITY_TOLERANCE_PX / max(framing.width, framing.height)
    if horizontal <= 0.0 or abs(horizontal - vertical) > slack:
        raise ValueError(
            f"Render target {size!r} does not match framing "
            f"{framing.size} at one density: {horizontal:.4f} against {vertical:.4f}"
        )
    return horizontal
