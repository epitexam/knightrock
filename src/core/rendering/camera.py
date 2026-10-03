import math

import pygame

from src.core.display.framing import DEFAULT_FRAMING, Framing
from src.core.settings import CameraShake

WorldRect = pygame.FRect | pygame.Rect
"""A world-space rectangle, whole-pixel or fractional.

Both, because the sprites being transformed carry a
:class:`pygame.Rect` -- ``Sprite.rect`` is an integer one -- while the
simulation produces :class:`pygame.FRect` from interpolated positions. Every
method on :class:`Camera` only ever reads ``x``, ``y``, ``width`` and
``height`` from its argument, so the distinction is not one any of them can
observe. Naming the union once is what keeps the annotations honest instead
of forcing every call site to convert a rect it only reads.
"""


def checked_density(density: float) -> float:
    """The pixel density, or refused.

    One implementation for everything that has to agree on the number: the
    viewport that builds the surface and the camera that maps rectangles onto
    it. A density below 1 is refused rather than clamped -- clamping to 1 is
    precisely the images-and-rectangles disagreement a render target is
    supposed to make impossible, and a window narrower than the framing is a
    legitimate answer, not an error to be hidden.
    """
    if density != density or density <= 0.0:  # NaN never compares equal to itself
        raise ValueError(f"The pixel density must be a positive number, got {density!r}")
    return density


class Camera:
    """Scrollable world camera: a translation and a magnification.

    The camera used to scale as well as translate, and the scale was the
    window's business -- it was built from the window's pixel size and a zoom
    constant, so the slice of world a player saw was a free variable of a video
    setting. ``Framing`` fixed that slice, which left nothing for a zoom to do:
    the camera only says where in the world the frame is looking, and how large
    a world unit is drawn is the render target's business.

    What changed is where that number comes from. It used to be a constant
    divided by the *window* size, which made the visible world a function of a
    video setting; it is now the density read back off the target
    (:meth:`for_target`), which the window cannot contradict because the target
    *is* the window.

    The mistake worth recording, because this branch shipped it once: making the
    camera a *pure translation* looks right -- the magnification belongs to the
    asset pipeline -- and it breaks the frame, because the magnification applies
    to the rectangles as much as to the images. At a 2x target a 64-unit sprite
    was scaled to 128px and then blitted into a 64px rect, and ``pygame.blit``
    **resamples the source to fit the destination** without saying so, so the
    world was drawn at half the density the framing claims and occupied a
    quarter of the frame. Pure translation is only correct when one world unit
    is one target pixel, which is a density of 1 and nothing else.

    That is also why the density is a float here and why :meth:`scaled_size`
    exists. A density of 1.889 means a 64-unit sprite is 121px, and a 121px
    image blitted into a 120.9px rect is resampled by ``pygame.blit`` -- the
    same failure, one rounding step later. So the rounding lives in exactly one
    method, and both the image and the rect it is blitted into are asked for it.

    ``apply()`` maps a world rectangle to exact target coordinates;
    ``apply_snapped()`` maps it to a whole-pixel rectangle whose size is
    :meth:`scaled_size`, which is what everything that blits an image uses.
    Every consumer (sprites, health bars, debug overlays, afterimages) goes
    through those two, so none of them can drift from the others.
    """

    def __init__(self, framing: Framing = DEFAULT_FRAMING, density: float = 1.0):
        self.offset = pygame.math.Vector2(0, 0)
        self.framing = framing
        #: Target pixels per world unit. The target is a letterbox rectangle for
        #: ``framing``, so this is not a free parameter: it is read back off the
        #: target rather than configured, by :meth:`for_target`.
        self.density = checked_density(density)
        self.world_width = 0.0
        self.world_height = 0.0
        self.trauma = 0.0
        self._shake_time = 0.0
        # Per-frame transform, recomputed once instead of per sprite. See
        # begin_frame.
        self._shake = pygame.math.Vector2(0.0, 0.0)
        self._shift = 0.0
        self._shift_y = 0.0
        self._viewport: pygame.FRect | None = None
        #: Offset the camera had when the last tick finished, so the draw can
        #: show it partway towards the current one. See begin_frame.
        self._previous_offset = pygame.math.Vector2(0.0, 0.0)

    @classmethod
    def for_target(cls, target: pygame.Surface, framing: Framing = DEFAULT_FRAMING) -> Camera:
        """A camera whose density is read off the render target.

        Deriving it from the surface it has to draw into is what keeps the two
        from disagreeing: a density passed alongside a target that implies
        another one produces a frame whose rectangles and images do not match,
        and nothing about that is visible until the level looks wrong.
        """
        from src.core.display.letterbox import density_for

        return cls(framing, density_for(target.get_size(), framing))

    def set_target(self, target: pygame.Surface) -> None:
        """Adopt a new render target and re-read the density from it.

        The camera's offset, shake and framing are untouched: a window resize
        is a sharpness decision, not a change of what is being looked at. Only
        the density moves, and it has to move here rather than in the renderer --
        a renderer holding its own copy of the number is how the images and the
        rectangles end up scaled differently.
        """
        self.density = Camera.for_target(target, self.framing).density
        self._viewport = None

    def scaled_size(self, size: tuple[float, float]) -> tuple[int, int]:
        """A world size in whole target pixels.

        The one rounding rule in the rendering path. A sprite's image is
        magnified to this size and blitted into a rectangle of this size, so
        ``pygame.blit`` is never asked to fit one into the other and never
        resamples behind our back. Anything that rounds a size for a blit
        without asking here is the bug this method exists to make impossible.

        **Up**, not to the nearest. That is not a preference, it is what makes
        :meth:`apply_snapped` gap-free: the position there is rounded *down*, and
        the difference between two rounded positions is at least ``floor(step)``
        and at most ``ceil(step)``. A size of ``round(step)`` is smaller than
        ``ceil(step)`` whenever the step's fraction is under a half, so a run of
        tiles drifts apart by a pixel every few tiles and a line of background
        opens through the terrain. Measured at density 0.5 with a 138.5-unit
        sprite: step 69.25, size 69, and the neighbour started one pixel after
        the previous one ended. With ``ceil`` the neighbour can at worst overlap
        by a pixel, which is invisible, against a gap, which is not.

        Takes floats because a world rect is fractional -- a tile is 64 units but
        a player's hurtbox is not -- and rounds both axes the same way, so a
        rectangle and the image drawn into it always agree.
        """
        return (
            max(1, math.ceil(size[0] * self.density)),
            max(1, math.ceil(size[1] * self.density)),
        )

    def begin_frame(self, alpha: float = 1.0) -> None:
        """Recompute the per-frame transform, once for the whole draw pass.

        ``is_visible`` and ``apply`` run once per visible sprite, ~1000 times
        per frame on a full level, and both used to rebuild their inputs every
        call: an ``FRect`` viewport per cull, and a fresh ``Vector2`` plus two
        ``sin``/``cos`` for the shake per transform. All of it is constant
        across a frame -- the camera does not move while a frame is being
        drawn -- so the values are derived here and read afterwards.

        ``alpha`` is the position inside the pending simulation tick, in
        [0, 1], and the offset is blended from where it was when the last tick
        finished towards where the tick just left it. Blending the *camera*
        rather than each sprite is what keeps the frame coherent: every sprite
        then moves by the same amount, so a sprite that only just entered the
        view cannot sit ahead of its interpolated neighbours and leave a seam
        of background along the leading edge. It also keeps the debug overlay
        aligned for free, since the overlay maps through this same transform.

        Any code that mutates the camera between frames must call this, or go
        through ``follow`` which does.
        """
        self._shake = self.shake_offset()
        alpha = min(max(alpha, 0.0), 1.0)
        x = self._previous_offset.x + (self.offset.x - self._previous_offset.x) * alpha
        y = self._previous_offset.y + (self.offset.y - self._previous_offset.y) * alpha
        self._shift = -x + self._shake.x
        self._shift_y = -y + self._shake.y
        self._viewport = pygame.FRect(x, y, self.viewport_width, self.viewport_height)

    def _ensure_frame(self) -> None:
        if self._viewport is None:
            self.begin_frame()

    @property
    def viewport(self) -> pygame.FRect:
        """The world rectangle the frame is looking at.

        Read by the spatial cull, which needs the same rectangle
        :meth:`is_visible` tests against. Exposed as a property so the frame
        is resolved through :meth:`begin_frame` like every other consumer,
        rather than by a caller reaching for ``_viewport``.
        """
        self._ensure_frame()
        assert self._viewport is not None
        return self._viewport

    @property
    def viewport_width(self) -> float:
        """Visible world width: the framing, which does not depend on the window."""
        return self.framing.width

    @property
    def viewport_height(self) -> float:
        """Visible world height: the framing, which does not depend on the window."""
        return self.framing.height

    def set_world_size(self, world_width: float, world_height: float) -> None:
        """Tell the camera how big the level is, so it can clamp against it."""
        self.world_width = world_width
        self.world_height = world_height

    def follow(self, target_rect: pygame.FRect, delta_time: float) -> None:
        # Where the draw left off last frame: the next begin_frame blends from
        # here towards wherever this tick ends up.
        self._previous_offset.update(self.offset.x, self.offset.y)
        target_x = target_rect.centerx - self.viewport_width / 2.0
        target_y = target_rect.centery - self.viewport_height / 2.0

        smoothing_factor = min(1.0, 8.0 * delta_time)
        self.offset.x += (target_x - self.offset.x) * smoothing_factor
        self.offset.y += (target_y - self.offset.y) * smoothing_factor

        self.advance_shake(delta_time)

        self._clamp_to_world()
        self._viewport = None

    def advance_shake(self, delta_time: float) -> None:
        """Age the impact shake by one tick: decay its trauma and move its phase.

        Split out of :meth:`follow`, which used to own this bookkeeping as a
        side effect of positioning. The level pipeline freezes the camera on
        the tick the player dies -- a dead body does not move, so following it
        would be pointless -- and that skip also froze the shake with it. The
        killing blow feeds trauma on the very tick it lands (the impact rule
        keys off the knockback, not off the death), so the shake was held at
        full amplitude, offsetting the entire frame by a constant non-zero
        vector for the whole death window instead of decaying over the fraction
        of a second it is supposed to last. It read as the whole screen
        trembling rather than as one impact, because ``begin_frame`` bakes this
        single vector into the shift every sprite is drawn through.

        So the shake ages whether or not the camera is following anybody.
        :meth:`follow` still calls it, keeping the two in lockstep for a living
        player; a caller that skipped ``follow`` for its own reasons has to age
        the shake itself.
        """
        self._shake_time += delta_time
        self.trauma = max(0.0, self.trauma - CameraShake.DECAY_PER_S * delta_time)

    def add_trauma(self, amount: float) -> None:
        """Feed impact shake (clamped); heavy launches shake the most."""
        self.trauma = min(1.0, self.trauma + max(0.0, amount))

    def shake_offset(self) -> pygame.math.Vector2:
        """Deterministic sine offset: same ticks always give same pixels."""
        magnitude = self.trauma * self.trauma * CameraShake.MAX_PX
        return pygame.math.Vector2(
            magnitude * math.sin(self._shake_time * CameraShake.FREQUENCY),
            magnitude * math.cos(self._shake_time * CameraShake.FREQUENCY * 1.31),
        )

    def _clamp_to_world(self) -> None:
        if self.world_width <= 0 or self.world_height <= 0:
            return
        view_w, view_h = self.viewport_width, self.viewport_height
        if self.world_width > view_w:
            self.offset.x = max(0.0, min(self.offset.x, self.world_width - view_w))
        else:
            self.offset.x = -(view_w - self.world_width) / 2.0
        if self.world_height > view_h:
            self.offset.y = max(0.0, min(self.offset.y, self.world_height - view_h))
        else:
            self.offset.y = -(view_h - self.world_height) / 2.0

    def apply(self, rect: WorldRect) -> pygame.FRect:
        """Map a world rectangle to exact target coordinates.

        Fractional on purpose: this is geometry, used for interpolation and for
        anything that wants the true bounds. It is **not** what a blit wants --
        see :meth:`apply_snapped`.
        """
        self._ensure_frame()
        density = self.density
        return pygame.FRect(
            (rect.x + self._shift) * density,
            (rect.y + self._shift_y) * density,
            rect.width * density,
            rect.height * density,
        )

    def apply_snapped(self, rect: WorldRect) -> pygame.Rect:
        """Map a world rectangle to the whole-pixel rect an image is blitted into.

        Two rules, and both of them are load-bearing:

        - the **size** is :meth:`scaled_size`, the same number the magnified
          image was built with, so ``pygame.blit`` has nothing to resample. A
          destination one pixel off the source is enough for it to rebuild the
          image, silently, every frame.
        - the **position** is the exact one rounded *down*. Neighbouring tiles
          then either share a pixel column or overlap by one, and never leave a
          gap: the rounded positions of ``n`` and ``n+1`` differ by at least
          ``floor(size)`` and the size is ``round(size)``, which is never less.

        Rounding the position outward instead -- the old ``apply_covering`` --
        grew each rectangle to ``ceil`` of its true bounds, which at a fractional
        density no longer matched the image and reintroduced the resampling this
        is here to prevent.
        """
        self._ensure_frame()
        exact = self.apply(rect)
        width, height = self.scaled_size((rect.width, rect.height))
        return pygame.Rect(math.floor(exact.x), math.floor(exact.y), width, height)

    def is_visible(self, rect: WorldRect) -> bool:
        """Check if a world rectangle intersects the framing rect.

        Accepts an integer :class:`pygame.Rect` as well as an
        :class:`pygame.FRect` because the sprites being culled carry one:
        ``Sprite.rect`` is either, and the only thing asked of the argument is
        an intersection.

        Args:
            rect: The world-space rectangle to check.

        Returns:
            True if the rectangle intersects the framing, False otherwise.
        """
        self._ensure_frame()
        assert self._viewport is not None
        return self._viewport.colliderect(rect)
