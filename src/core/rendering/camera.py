import math

import pygame

from src.core.display.framing import DEFAULT_FRAMING, Framing, checked_render_scale
from src.core.settings import CameraShake


class Camera:
    """Scrollable world camera: a pure translation.

    The camera used to scale as well as translate, and the scale was the
    window's business -- it was built from the window's pixel size and a zoom
    constant, so the slice of world a player saw was a free variable of a video
    setting. ``Framing`` fixed that slice, which left nothing for a zoom to do:
    how large the world is drawn is now the render target's business, decided
    once at load, and the camera only says where in the world the frame is
    looking.

    There is a scale, and it is not optional: the render target is
    ``framing * scale`` pixels, so a world rectangle has to be multiplied to
    land on the right pixels. What changed is where the scale comes from. It
    used to be a constant divided by the *window* size, which made the visible
    world a function of a video setting; it is now the integer the render target
    was built with, which the window cannot influence.

    The mistake worth recording: making the camera a *pure translation* looks
    right -- the magnification belongs to the asset pipeline -- and it breaks
    the frame, because the magnification applies to the rectangles as much as to
    the images. At a 2x target a 64-unit sprite was scaled to 128px and then
    blitted into a 64px rect, and ``pygame.blit`` resizes the source to fit the
    destination, so the world was drawn at half the density the framing claims
    and occupied a quarter of the frame. Pure translation is only correct when
    one world unit is one target pixel, i.e. at a 1x target.

    ``apply()`` maps a world rectangle to render-target coordinates by
    translating it; ``is_visible()`` culls against the framing rect. Every
    consumer (sprites, health bars, debug overlays, afterimages) goes through
    those two, so none of them can drift from the others.
    """

    def __init__(self, framing: Framing = DEFAULT_FRAMING, scale: int = 1):
        self.offset = pygame.math.Vector2(0, 0)
        self.framing = framing
        #: Target pixels per world unit. The target is ``framing * scale``, so
        #: this is not a free parameter: it is read back off the target rather
        #: than configured, by :meth:`for_target`.
        self.scale = checked_render_scale(scale)
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
        """A camera whose scale is read off the render target.

        Deriving the scale from the surface it has to draw into is what keeps
        the two from disagreeing: a scale passed alongside a target of a
        different size produces a frame whose rectangles and images do not
        match, and nothing about that is visible until the level looks wrong.

        A non-integral ratio means the target does not match the framing, which
        is a wiring mistake rather than a configuration; it is refused rather
        than rounded, because a rounded scale would draw the world at a density
        the player never asked for and the framing contract would no longer
        describe what is on screen.
        """
        width = target.get_width() / framing.width
        height = target.get_height() / framing.height
        scale = round(width)
        if scale < 1 or abs(width - scale) > 1e-6 or abs(height - scale) > 1e-6:
            raise ValueError(
                f"Render target {target.get_size()} does not match framing "
                f"{framing.size} times an integer scale"
            )
        return cls(framing, scale)

    def set_target(self, target: pygame.Surface) -> None:
        """Adopt a new render target and re-read the scale from it.

        The camera's offset, shake and framing are untouched: a render-scale
        change is a sharpness decision, not a change of what is being looked at.
        Only the scale moves, and it has to move here rather than in the
        renderer -- a renderer holding its own copy of the number is how the
        images and the rectangles end up scaled differently.
        """
        adopted = Camera.for_target(target, self.framing)
        self.scale = adopted.scale
        self._viewport = None

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

        self._shake_time += delta_time
        self.trauma = max(0.0, self.trauma - CameraShake.DECAY_PER_S * delta_time)

        self._clamp_to_world()
        self._viewport = None

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

    def apply(self, rect: pygame.FRect) -> pygame.FRect:
        """Map a world rectangle to render-target coordinates."""
        self._ensure_frame()
        scale = self.scale
        return pygame.FRect(
            (rect.x + self._shift) * scale,
            (rect.y + self._shift_y) * scale,
            rect.width * scale,
            rect.height * scale,
        )

    def apply_covering(self, rect: pygame.FRect) -> pygame.Rect:
        """Target rectangle for a world rect, rounded *outward* to cover it.

        ``apply`` returns exact fractional bounds, and ``pygame.Rect`` built
        from those truncates them. Truncation always rounds a rectangle *in*:
        a tile at the right edge of the world comes out one pixel short of the
        edge it was meant to reach, and the last column of the frame is then
        never painted by anything and keeps whatever the background fill left
        there. It only shows once the camera is pushed against the clamp, which
        in practice means when the player dashes into a corner of the map.

        Rounding the near edges down and the far edges up keeps the true extent:
        the rect grows by at most a pixel, so neighbours may overlap by a pixel
        instead of leaving a gap between them, and no pixel the caller meant to
        cover is dropped.
        """
        self._ensure_frame()
        exact = self.apply(rect)
        left = math.floor(exact.x)
        top = math.floor(exact.y)
        right = math.ceil(exact.right)
        bottom = math.ceil(exact.bottom)
        return pygame.Rect(left, top, right - left, bottom - top)

    def is_visible(self, rect: pygame.FRect) -> bool:
        """Check if a world rectangle intersects the framing rect.

        Args:
            rect: The world-space rectangle to check.

        Returns:
            True if the rectangle intersects the framing, False otherwise.
        """
        self._ensure_frame()
        assert self._viewport is not None
        return self._viewport.colliderect(rect)
