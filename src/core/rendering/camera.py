import math

import pygame

from src.core.settings import CameraShake, GameplayCamera


class Camera:
    """Scrollable world camera with a fixed gameplay zoom.

    The camera keeps two distinct notions:

    - the *display* size (the window), which is the canvas everything is
      painted on;
    - the *world viewport* size, which is the visible slice of the world
      once the zoom is taken into account.

    ``apply()`` maps a world rectangle to screen coordinates by translating
    it and then scaling it by ``zoom``; ``is_visible()`` culls against the
    zoomed world viewport. Every consumer of the camera (sprites, health
    bars, debug overlays, afterimages) therefore follows the zoom without any
    extra work, and a higher zoom shows *less* of the world.

    ``zoom = 1`` keeps the previous de-zoomed behaviour.
    """

    def __init__(self, width: int, height: int, zoom: float = GameplayCamera.ZOOM):
        self.offset = pygame.math.Vector2(0, 0)
        self.width = width
        self.height = height
        self.zoom = self._valid_zoom(zoom)
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
        through ``follow``/``set_viewport_size``/``set_zoom`` which do.
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

    @staticmethod
    def _valid_zoom(zoom: float) -> float:
        if zoom <= 0.0:
            raise ValueError("Camera zoom must be strictly positive")
        return zoom

    @property
    def viewport_width(self) -> float:
        """Visible world width, i.e. the display width divided by the zoom."""
        return self.width / self.zoom

    @property
    def viewport_height(self) -> float:
        """Visible world height, i.e. the display height divided by the zoom."""
        return self.height / self.zoom

    def set_zoom(self, zoom: float) -> None:
        """Change the framing and re-clamp so the viewport stays in world."""
        self.zoom = self._valid_zoom(zoom)
        self._clamp_to_world()
        self._viewport = None

    def set_viewport_size(self, width: int, height: int) -> None:
        """Update the display size (a resolution or a window change)."""
        self.width = width
        self.height = height
        self._clamp_to_world()
        self._viewport = None

    def set_world_size(self, world_width: float, world_height: float) -> None:
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
        """Map a world rectangle to screen coordinates (translate + zoom)."""
        self._ensure_frame()
        zoom = self.zoom
        return pygame.FRect(
            (rect.x + self._shift) * zoom,
            (rect.y + self._shift_y) * zoom,
            rect.width * zoom,
            rect.height * zoom,
        )

    def apply_covering(self, rect: pygame.FRect) -> pygame.Rect:
        """Screen rectangle for a world rect, rounded *outward* to cover it.

        ``apply`` returns exact fractional bounds, and ``pygame.Rect`` built
        from those truncates them. Truncation always rounds a rectangle *in*:
        the world tile at the far edge of a level maps to x 1427.5..1440.0 on
        a 1440-wide screen, and comes out as ``Rect(1427, .., 12)``, which
        stops at 1438. The last column of the window is then never painted by
        anything and keeps whatever the background fill left there -- a
        one-pixel line of sky down the right edge of the screen, and another
        along the bottom. It only shows once the camera is pushed against the
        clamp, which in practice means when the player dashes into a corner of
        the map.

        Rounding the near edges down and the far edges up keeps the true
        extent: the rect grows by at most a pixel, so neighbours may overlap
        by a pixel instead of leaving a gap between them, and no pixel the
        caller meant to cover is dropped.

        The far edges are taken from ``apply``'s own result rather than
        recomputed from the world rect. ``(x + w) * z`` and ``x * z + w * z``
        disagree in the last bit, and ``ceil`` of a value one bit below the
        true one lands a whole pixel short, which is the very bug this
        replaces.
        """
        self._ensure_frame()
        exact = self.apply(rect)
        left = math.floor(exact.x)
        top = math.floor(exact.y)
        right = math.ceil(exact.right)
        bottom = math.ceil(exact.bottom)
        return pygame.Rect(left, top, right - left, bottom - top)

    def is_visible(self, rect: pygame.FRect) -> bool:
        """Check if a world rectangle intersects the zoomed camera viewport.

        Args:
            rect: The world-space rectangle to check.

        Returns:
            True if the rectangle intersects the camera viewport, False otherwise.
        """
        self._ensure_frame()
        assert self._viewport is not None
        return self._viewport.colliderect(rect)
