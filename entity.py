import pygame
from pygame.math import Vector2

from settings import GRAVITY, WINDOW_HEIGHT, WINDOW_WIDTH


class Entity(pygame.sprite.Sprite):
    def __init__(self, pos, size, color, groups, collision_sprites):
        super().__init__(groups)
        self.image = pygame.Surface(size)
        self.image.fill(color)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.old_rect: pygame.FRect = self.rect.copy()

        self.collision_sprites = collision_sprites
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.velocity = Vector2(0, 0)

        self.normal_gravity = GRAVITY
        self.slide_gravity = GRAVITY * 0.15
        self.max_slide_speed = 80

    def _is_wall_sliding(self) -> bool:
        return False

    def _on_floor_contact(self):
        pass

    def _on_wall_contact(self):
        pass

    def apply_gravity(self, delta_time):
        if self._is_wall_sliding():
            self.velocity.y += self.slide_gravity * delta_time
            self.velocity.y = min(self.velocity.y, self.max_slide_speed)
        else:
            self.velocity.y += self.normal_gravity * delta_time

    def check_contact(self):
        if self.rect is None:
            return

        height_quarter = self.rect.height / 4
        half_height = self.rect.height / 2

        floor_rect = pygame.FRect(self.rect.bottomleft, (self.rect.width, 2))
        right_rect = pygame.FRect(
            self.rect.topright + Vector2(0, height_quarter), (2, half_height)
        )
        left_rect = pygame.FRect(
            self.rect.topleft + Vector2(-2, height_quarter), (2, half_height)
        )

        collide_rects = []
        for sprite in self.collision_sprites:
            if (
                sprite is not None
                and hasattr(sprite, "rect")
                and sprite.rect is not None
            ):
                collide_rects.append(sprite.rect)

        self.on_surface["floor"] = floor_rect.collidelist(collide_rects) >= 0
        self.on_surface["right"] = right_rect.collidelist(collide_rects) >= 0
        self.on_surface["left"] = left_rect.collidelist(collide_rects) >= 0

        if self.on_surface["floor"]:
            self._on_floor_contact()
        elif self.on_surface["left"] or self.on_surface["right"]:
            self._on_wall_contact()

    def handle_collisions(self, axis):
        if self.rect is None:
            return

        for sprite in pygame.sprite.spritecollide(self, self.collision_sprites, False):
            if sprite is None or not hasattr(sprite, "rect") or sprite.rect is None:
                continue

            is_moving_platform = hasattr(sprite, "old_rect")

            if axis == "horizontal":
                if self.old_rect.right <= sprite.old_rect.left:
                    self.rect.right = sprite.rect.left
                elif self.old_rect.left >= sprite.old_rect.right:
                    self.rect.left = sprite.rect.right

                if not is_moving_platform:
                    self.velocity.x = 0

            elif axis == "vertical":
                if self.old_rect.bottom <= sprite.old_rect.top:
                    self.rect.bottom = sprite.rect.top
                elif self.old_rect.top >= sprite.old_rect.bottom:
                    self.rect.top = sprite.rect.bottom
                self.velocity.y = 0

    def apply_moving_platform(self, moving_platforms):
        if not self.on_surface["floor"]:
            return

        for platform in moving_platforms:
            vertical_dist = self.rect.bottom - platform.old_rect.top
            if not (-2 <= vertical_dist <= 16):
                continue

            overlap = min(self.rect.right, platform.old_rect.right) - max(
                self.rect.left, platform.old_rect.left
            )
            if overlap <= 0:
                continue

            dx = platform.rect.x - platform.old_rect.x
            dy = platform.rect.y - platform.old_rect.y
            self.rect.x += dx
            self.rect.y += dy
            break

    def reset_position(self):
        if self.rect is None:
            return
        self.rect.center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        self.velocity = Vector2(0, 0)
        self.old_rect = self.rect.copy()

    def update(self, delta_time):
        if self.rect is None:
            return
        self.old_rect = self.rect.copy()
