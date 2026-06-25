"""
Simple camera that follows a target entity.
"""

import pygame


class Camera:
    def __init__(self, width: int, height: int):
        self.offset = pygame.math.Vector2(0, 0)
        self.width = width
        self.height = height

    def follow(self, target_rect: pygame.FRect) -> None:
        """Center the camera on the given rect."""
        self.offset.x = target_rect.centerx - self.width // 2
        self.offset.y = target_rect.centery - self.height // 2

    def apply(self, rect: pygame.FRect) -> pygame.FRect:
        """Return a rect shifted by the camera offset."""
        return rect.move(-self.offset.x, -self.offset.y)

    def apply_to_surface(
        self, surface: pygame.Surface, rect: pygame.FRect
    ) -> pygame.FRect:
        """Return the blit position for a surface."""
        return rect.move(-self.offset.x, -self.offset.y)
