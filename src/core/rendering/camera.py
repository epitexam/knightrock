import math

import pygame

from src.core.settings import CameraShake


class Camera:
    def __init__(self, width: int, height: int):
        self.offset = pygame.math.Vector2(0, 0)
        self.width = width
        self.height = height
        self.world_width = 0.0
        self.world_height = 0.0
        self.trauma = 0.0
        self._shake_time = 0.0

    def set_world_size(self, world_width: float, world_height: float) -> None:
        self.world_width = world_width
        self.world_height = world_height

    def follow(self, target_rect: pygame.FRect, delta_time: float) -> None:
        target_x = target_rect.centerx - self.width / 2.0
        target_y = target_rect.centery - self.height / 2.0

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
        if self.world_width > self.width:
            self.offset.x = max(0.0, min(self.offset.x, self.world_width - self.width))
        else:
            self.offset.x = -(self.width - self.world_width) / 2.0
        if self.world_height > self.height:
            self.offset.y = max(0.0, min(self.offset.y, self.world_height - self.height))
        else:
            self.offset.y = -(self.height - self.world_height) / 2.0

    def apply(self, rect: pygame.FRect) -> pygame.FRect:
        shake = self.shake_offset()
        return rect.move(-self.offset.x + shake.x, -self.offset.y + shake.y)

    def is_visible(self, rect: pygame.FRect) -> bool:
        """Check if a rectangle is visible within the camera viewport.

        Args:
            rect: The world-space rectangle to check.

        Returns:
            True if the rectangle intersects the camera viewport, False otherwise.
        """
        camera_rect = pygame.FRect(self.offset.x, self.offset.y, self.width, self.height)
        return camera_rect.colliderect(rect)
