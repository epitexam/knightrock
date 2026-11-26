"""How much of a window the picture occupies, and how many pixels a world unit is.

- A window of any shape is fitted to the framing's aspect under a policy
  (:func:`picture`).
- That rectangle is the render target, so the frame is blitted 1:1 and never
  resampled (scaling a fixed target onto the window cost 4 ms a frame and
  blurred the art).
- The density is read back off the rectangle (:func:`density_for`), so it
  cannot disagree with it.

``ZOOM`` fills the window by cropping a picture of the framing's shape, so it
never shows more world. Widening the framing to fill the window ("expand") is
not offered: how much of the level is visible must not depend on a video
setting.
"""

from enum import StrEnum

import pygame

from .framing import DEFAULT_FRAMING, Framing

#: How far the two axes' densities may disagree, in pixels across the frame:
#: the rounding of a rectangle to whole pixels, and no more. Beyond it the frame
#: would be stretched on one axis.
DENSITY_TOLERANCE_PX = 1.0


class FitPolicy(StrEnum):
    """The ways a picture meets a window. A ``StrEnum``: the value is saved."""

    BARS = "bars"
    INTEGER = "integer"
    ZOOM = "zoom"
    #: Whole pixels when they cost little, bars otherwise. See :func:`picture`.
    AUTO = "auto"


#: How much of the bars picture a whole-pixel picture must keep for ``AUTO`` to
#: take it. Below this the whole-pixel picture is a small box in a big frame,
#: and uneven pixels on a picture that fills the window are the better trade.
AUTO_MIN_COVERAGE = 0.85


class Picture:
    """Where the picture sits, where it comes from, and what surrounds it.

    ``target`` is the render rectangle, ``source`` the part of it the window
    shows, ``dest`` where that lands on the window. For bars and integer the
    source is the whole target; for zoom the dest is the window and the source
    a centred crop. ``bars`` is the window minus ``dest``.
    """

    __slots__ = ("bars", "dest", "source", "target", "window")

    def __init__(
        self,
        target: pygame.Rect,
        source: pygame.Rect,
        dest: pygame.Rect,
        window: tuple[int, int],
    ) -> None:
        self.target = target
        self.source = source
        self.dest = dest
        self.window = window
        self.bars = self._fit_bars()

    @property
    def covered(self) -> bool:
        """Whether the picture reaches every corner of the window."""
        return self.dest.topleft == (0, 0) and self.dest.size == self.window

    def _fit_bars(self) -> tuple[pygame.Rect, ...]:
        width, height = self.window
        return tuple(
            bar
            for bar in (
                pygame.Rect(0, 0, self.dest.x, height),
                pygame.Rect(self.dest.right, 0, max(0, width - self.dest.right), height),
                pygame.Rect(self.dest.x, 0, self.dest.width, self.dest.y),
                pygame.Rect(
                    self.dest.x,
                    self.dest.bottom,
                    self.dest.width,
                    max(0, height - self.dest.bottom),
                ),
            )
            if bar.width > 0 and bar.height > 0
        )

    def __repr__(self) -> str:
        return (
            f"Picture(target={tuple(self.target)}, source={tuple(self.source)}, "
            f"dest={tuple(self.dest)}, bars={len(self.bars)})"
        )


def picture(
    window: tuple[int, int],
    framing: Framing = DEFAULT_FRAMING,
    policy: FitPolicy | str = FitPolicy.BARS,
) -> Picture:
    """Where a window's picture goes, under ``policy``.

    Every branch ends with a target that is a whole number of pixels and at the
    framing's aspect to within that rounding, so :func:`density_for` reads one
    exact density off it and the world is never stretched.
    """
    chosen = FitPolicy(policy)
    width, height = window
    if width <= 0 or height <= 0:
        rect = pygame.Rect(0, 0, 1, 1)
        return Picture(rect, pygame.Rect(0, 0, 1, 1), rect, (1, 1))
    if chosen is FitPolicy.ZOOM:
        return _zoom(window, framing)
    if chosen is FitPolicy.AUTO:
        return _auto(window, framing)
    return _fit_inside(window, framing, chosen is FitPolicy.INTEGER)


def _auto(window: tuple[int, int], framing: Framing) -> Picture:
    """Whole pixels if they keep :data:`AUTO_MIN_COVERAGE` of the picture, bars otherwise.

    Under bars the art's pixels come out of uneven sizes; a whole multiple is
    exact but can be much smaller than the window.
    """
    bars = _fit_inside(window, framing, whole_multiples=False)
    if not fits_whole_pixel(window, framing):
        return bars
    whole = _fit_inside(window, framing, whole_multiples=True)
    kept = (whole.dest.width * whole.dest.height) / max(1, bars.dest.width * bars.dest.height)
    return whole if kept >= AUTO_MIN_COVERAGE else bars


def _fit_inside(window: tuple[int, int], framing: Framing, whole_multiples: bool) -> Picture:
    """The rectangle carrying the picture, centred in the window, bars around it."""
    width, height = window
    scale = min(width / framing.width, height / framing.height)
    if whole_multiples:
        whole = int(scale)
        if whole >= 1:
            scale = float(whole)
        # Below one whole multiple there is nothing to snap to: the fitted
        # rectangle is kept, and the menu says the policy does nothing here.
    target_w = max(1, min(width, round(framing.width * scale)))
    target_h = max(1, min(height, round(framing.height * scale)))
    target = pygame.Rect((width - target_w) // 2, (height - target_h) // 2, target_w, target_h)
    return Picture(target, pygame.Rect((0, 0), target.size), target, window)


def _zoom(window: tuple[int, int], framing: Framing) -> Picture:
    """Cover the window with a picture of the framing's shape, and crop it.

    The world shown is a subset of the framing, never a superset.
    """
    width, height = window
    scale = max(width / framing.width, height / framing.height)
    target_w = max(width, round(framing.width * scale))
    target_h = max(height, round(framing.height * scale))
    crop = pygame.Rect((target_w - width) // 2, (target_h - height) // 2, width, height)
    dest = pygame.Rect(0, 0, width, height)
    return Picture(pygame.Rect(0, 0, target_w, target_h), crop, dest, window)


def fits_whole_pixel(window: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> bool:
    """Whether a whole multiple of the framing fits in ``window``."""
    if window[0] <= 0 or window[1] <= 0:
        return False
    return min(window[0] / framing.width, window[1] / framing.height) >= 1.0


def already_a_whole_multiple(window: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> bool:
    """Whether the window *already is* a whole multiple of the framing.

    Then bars and integer give the same picture, and the menu says so rather
    than offering a change that shows nothing. A window too small for any whole
    multiple is the other case, and answers ``False``.
    """
    if not fits_whole_pixel(window, framing):
        return False
    return (
        picture(window, framing, FitPolicy.BARS).dest.size
        == picture(window, framing, FitPolicy.INTEGER).dest.size
    )


def effective_fit(fit: FitPolicy, pixel_perfect: bool) -> FitPolicy:
    """The fit in force, from the saved policy and the older whole-pixel flag.

    The flag (from files older than the fit picker) turns a policy that was
    never chosen into ``integer``; a chosen policy is kept. A free function so
    the runtime and the menu read the same rule.
    """
    if pixel_perfect and fit in (FitPolicy.BARS, FitPolicy.AUTO):
        # BARS was the default before AUTO was; both mean "never chosen".
        return FitPolicy.INTEGER
    return fit


def density_for(size: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> float:
    """Target pixels per world unit, read off a target of ``size``.

    Raises when the two axes disagree: that is a bug upstream, not a rounding.
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
