import pygame


class Camera:
    def __init__(self, width: int, height: int):
        self.offset = pygame.math.Vector2(0, 0)
        self.width = width
        self.height = height
        self.world_width = 0.0
        self.world_height = 0.0

    def set_world_size(self, world_width: float, world_height: float) -> None:
        self.world_width = world_width
        self.world_height = world_height

    def follow(self, target_rect: pygame.FRect, delta_time: float) -> None:
        target_x = target_rect.centerx - self.width / 2.0
        target_y = target_rect.centery - self.height / 2.0

        smoothing_factor = min(1.0, 8.0 * delta_time)
        self.offset.x += (target_x - self.offset.x) * smoothing_factor
        self.offset.y += (target_y - self.offset.y) * smoothing_factor

        self._clamp_to_world()

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
        return rect.move(-self.offset.x, -self.offset.y)