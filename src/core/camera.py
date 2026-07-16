"""
Camera system with frame-rate independent smoothing.
"""

import pygame


class Camera:
    """Track a viewport offset for rendering with optional lerp follow logic."""

    def __init__(self, width: int, height: int):
        """Initialize the Camera with viewport dimensions and default offset."""
        self.offset = pygame.math.Vector2(0, 0)
        self.width = width
        self.height = height

    def follow(self, target_rect: pygame.FRect, delta_time: float) -> None:
        """Smoothly center the camera on the given rect using linear interpolation."""
        target_x = target_rect.centerx - self.width / 2.0
        target_y = target_rect.centery - self.height / 2.0
        
        smoothing_factor = min(1.0, 8.0 * delta_time)
        self.offset.x += (target_x - self.offset.x) * smoothing_factor
        self.offset.y += (target_y - self.offset.y) * smoothing_factor

    def apply(self, rect: pygame.FRect) -> pygame.FRect:
        """Return a rect shifted by the current camera offset."""
        return rect.move(-self.offset.x, -self.offset.y)