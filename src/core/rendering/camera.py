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

    def set_viewport_size(self, width: int, height: int) -> None:
        """Update the display size (a resolution or a window change)."""
        self.width = width
        self.height = height
        self._clamp_to_world()

    def set_world_size(self, world_width: float, world_height: float) -> None:
        self.world_width = world_width
        self.world_height = world_height

    def follow(self, target_rect: pygame.FRect, delta_time: float) -> None:
        target_x = target_rect.centerx - self.viewport_width / 2.0
        target_y = target_rect.centery - self.viewport_height / 2.0

        smoothing_factor = min(1.0, 8.0 * delta_time)
        self.offset.x += (target_x - self.offset.x) * smoothing_factor
        self.offset.y += (target_y - self.offset.y) * smoothing_factor

        self._shake_time += delta_time
        self.trauma = max(0.0, self.trauma - CameraShake.DECAY_PER_S * delta_time)

        self._clamp_to_world()

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
        shake = self.shake_offset()
        zoom = self.zoom
        screen = rect.move(-self.offset.x + shake.x, -self.offset.y + shake.y)
        return pygame.FRect(
            screen.x * zoom,
            screen.y * zoom,
            screen.width * zoom,
            screen.height * zoom,
        )

    def is_visible(self, rect: pygame.FRect) -> bool:
        """Check if a world rectangle intersects the zoomed camera viewport.

        Args:
            rect: The world-space rectangle to check.

        Returns:
            True if the rectangle intersects the camera viewport, False otherwise.
        """
        camera_rect = pygame.FRect(
            self.offset.x, self.offset.y, self.viewport_width, self.viewport_height
        )
        return camera_rect.colliderect(rect)
