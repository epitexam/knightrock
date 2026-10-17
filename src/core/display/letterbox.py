"""How much of a window the picture occupies, and how many pixels a world unit is.

The whole display system is three lines of arithmetic, and they live here so
that there is exactly one copy of each:

- a window of any shape is fitted to the framing's aspect, under a policy the
  player chose (:func:`picture`);
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

Why zoom is safe, and "expand" is not offered
---------------------------------------------
The framing is a gameplay contract: how much of the level is visible decides the
suspense, and it is fixed in world units precisely so a video setting cannot
change it. ``ZOOM`` respects that. It fills the window with a picture at the
framing's aspect and shows the window a centred *crop*, so a 21:9 player sees the
framing's 1152x648 world units and loses the edges of the image rather than
seeing a wider slice of the level.

Widening the framing to fill the window -- Godot's "expand" -- would show *more
world* on a wide screen, which is the exact defect the fixed framing closed: the
amount of level visible became a function of a video setting. It is not offered
as a policy for that reason, and there is no code path for it to be offered from.
"""

from enum import StrEnum

import pygame

from .framing import DEFAULT_FRAMING, Framing

#: How far the two axes' densities may disagree, expressed in pixels of target.
#:
#: Rounding a rectangle to whole pixels cannot preserve a ratio exactly, so a
#: target's two axes always imply densities that differ slightly. The bound is
#: "at most a pixel of mismatch across the whole frame": the framing's height in
#: pixels then misses the target's by no more than one, which is the rounding the
#: rectangle already made and cannot be seen. Beyond that the two axes are
#: describing different worlds, and the frame would be drawn anisotropically --
#: stretched on one axis only, which is the one thing a render target exists to
#: prevent.
DENSITY_TOLERANCE_PX = 1.0


class FitPolicy(StrEnum):
    """The ways a picture meets a window, as the video menu names them.

    A ``StrEnum`` because it is persisted: the settings file stores the value and
    has to read it back into the same enum the menu cycles, so the two cannot
    disagree about what a policy is called.
    """

    BARS = "bars"
    INTEGER = "integer"
    ZOOM = "zoom"


class Picture:
    """Where the picture sits, where it comes from, and what surrounds it.

    ``target`` is the render rectangle in target pixels. ``source`` is the part
    of that rectangle the window shows and ``dest`` is where it lands on the
    window. For bars and integer, ``source`` is the whole target and ``dest`` is
    a rectangle inside the window. For zoom, ``dest`` is the window and ``source``
    is a centred crop -- the only way to fill a window whose shape does not
    match the framing without ever showing more world than the framing allows.

    ``bars`` is the window minus ``dest``, empty when the window is covered. It
    is computed here rather than per frame because presenting a frame reads it
    every frame and it only moves when the window does.
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
    return _fit_inside(window, framing, chosen is FitPolicy.INTEGER)


def _fit_inside(window: tuple[int, int], framing: Framing, whole_multiples: bool) -> Picture:
    """The rectangle carrying the picture, centred in the window, bars around it."""
    width, height = window
    scale = min(width / framing.width, height / framing.height)
    if whole_multiples:
        whole = int(scale)
        if whole >= 1:
            scale = float(whole)
        # Below one whole multiple there is nothing to snap to, and clamping the
        # multiple *down* to the window would hand back a rectangle of the wrong
        # aspect -- which the density check refuses. So the fitted rectangle is
        # returned unchanged and the caller says the policy does nothing here.
    target_w = max(1, min(width, round(framing.width * scale)))
    target_h = max(1, min(height, round(framing.height * scale)))
    target = pygame.Rect((width - target_w) // 2, (height - target_h) // 2, target_w, target_h)
    return Picture(target, pygame.Rect((0, 0), target.size), target, window)


def _zoom(window: tuple[int, int], framing: Framing) -> Picture:
    """Cover the window with a picture of the framing's shape, and crop it.

    The target is larger than the window on at least one axis and exactly the
    framing's aspect, so the density stays single-valued. The window is centred
    in it, which means the world shown is a subset of the framing, never a
    superset.
    """
    width, height = window
    scale = max(width / framing.width, height / framing.height)
    target_w = max(width, round(framing.width * scale))
    target_h = max(height, round(framing.height * scale))
    crop = pygame.Rect((target_w - width) // 2, (target_h - height) // 2, width, height)
    dest = pygame.Rect(0, 0, width, height)
    return Picture(pygame.Rect(0, 0, target_w, target_h), crop, dest, window)


def fits_whole_pixel(window: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> bool:
    """Whether a whole multiple of the framing fits in ``window``.

    The integer policy has to know this before offering itself: on a window
    narrower than the framing there is no whole multiple to snap to, and the menu
    says that instead of pretending.
    """
    if window[0] <= 0 or window[1] <= 0:
        return False
    return min(window[0] / framing.width, window[1] / framing.height) >= 1.0


def already_a_whole_multiple(window: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> bool:
    """Whether the window is *already* sized to a whole multiple of the framing.

    ``fits_whole_pixel`` asks whether a whole multiple fits; this asks whether the
    window already is one. They disagree on exactly one class of window, and it is
    the class that reads as a broken row: a window already sized to a whole
    multiple, where :func:`picture` returns the same rectangle under bars and
    under integer. The setting is honoured and the picture does not move, which is
    correct -- there was nothing to snap to -- but the player pressing the row
    gets no picture at all, and a row that flips its label while the screen sits
    still is indistinguishable from a dead one.

    Rarer than the other case: only exact multiples of the framing, so a
    1152x648 or 2304x1296 window at the shipped framing, and a borderless desktop
    that happens to be exactly 2x.

    The ``fits_whole_pixel`` guard is not decoration, and it is what this function
    got wrong first. Without it, a window too small to hold a whole multiple also
    returns the same rectangle -- :func:`picture` hands the fitted one back
    unchanged -- so the comparison alone reports a window with no whole multiple
    in it as "already one". That is the other refusal, and the two have to stay
    distinguishable: a caller that checked this alone would tell a player with a
    window too small for the art that there is nothing left to do.
    """
    if not fits_whole_pixel(window, framing):
        return False
    return (
        picture(window, framing, FitPolicy.BARS).dest.size
        == picture(window, framing, FitPolicy.INTEGER).dest.size
    )


def effective_fit(fit: FitPolicy, pixel_perfect: bool) -> FitPolicy:
    """Resolve the fit policy a file's two names describe into the one in force.

    Whole-pixel art used to be its own row, stored as a boolean, and the fit
    picker is its successor: three named policies. A file written before the
    picker existed carries the flag and no policy, and the flag has to mean
    the integer policy rather than be lost -- a player who asked for whole pixels
    and opens a game that resamples their art has not been told anything, they
    have just been given a picture they did not ask for.

    The reconciliation is order-sensitive, and the order is the escaping clause:
    a file that *has* chosen a policy keeps it. The boolean is honoured only
    where the policy is still the default, so ``zoom`` from a v4 file is never
    overridden by a flag a v3 migration carried in. Only then does the flag
    promote ``bars`` to ``integer``.

    It is a free function rather than a method of :class:`Game` because both
    sides of the reconciliation need it at different times -- the runtime to
    draw with, and the menu read-out to describe with -- and the mixup between
    the two readers is exactly the bug this exists to close. A pure function of
    the two stored names can be handed to a test stand-in as-is, so the stand-in
    follows the same rule the runtime does.
    """
    if fit is not FitPolicy.BARS and pixel_perfect:
        return fit
    if pixel_perfect:
        return FitPolicy.INTEGER
    return fit


def density_for(size: tuple[int, int], framing: Framing = DEFAULT_FRAMING) -> float:
    """Target pixels per world unit, read off a target of ``size``.

    A refusal, not a clamp: a target whose two axes imply different densities is
    not the framing at some density, it is a mistake somewhere upstream, and
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
