import pygame
from pygame.math import Vector2

from settings import GRAVITY, WINDOW_HEIGHT, WINDOW_WIDTH


def _hitbox_collide(a, b):
    box_a = getattr(a, "hitbox", a.rect)
    box_b = getattr(b, "hitbox", b.rect)
    return box_a.colliderect(box_b)


class Entity(pygame.sprite.Sprite):
    def __init__(self, pos, size, color, groups, collision_sprites, hitbox_inflate=(0, 0)):
        super().__init__(groups)
        self.image = pygame.Surface(size)
        self.image.fill(color)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.hitbox: pygame.FRect = self.rect.inflate(*hitbox_inflate)
        self.hitbox.midbottom = self.rect.midbottom
        self.old_rect: pygame.FRect = self.hitbox.copy()
        self.attack_box: pygame.FRect | None = None

        self.collision_sprites = collision_sprites
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.velocity = Vector2(0, 0)

        self.normal_gravity = GRAVITY
        self.slide_gravity = GRAVITY * 0.15
        self.max_slide_speed = 80

    @property
    def hurtbox(self) -> pygame.FRect:
        return self.hitbox

    def sync_rects(self):
        self.rect.midbottom = self.hitbox.midbottom

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
        height_quarter = self.hitbox.height / 4
        half_height = self.hitbox.height / 2

        floor_rect = pygame.FRect(self.hitbox.bottomleft, (self.hitbox.width, 2))
        right_rect = pygame.FRect(self.hitbox.topright + Vector2(0, height_quarter), (2, half_height))
        left_rect = pygame.FRect(self.hitbox.topleft + Vector2(-2, height_quarter), (2, half_height))

        collide_rects = [
            s.rect for s in self.collision_sprites
            if s is not None and hasattr(s, "rect") and s.rect is not None
        ]

        self.on_surface["floor"] = floor_rect.collidelist(collide_rects) >= 0
        self.on_surface["right"] = right_rect.collidelist(collide_rects) >= 0
        self.on_surface["left"] = left_rect.collidelist(collide_rects) >= 0

        if self.on_surface["floor"]:
            self._on_floor_contact()
        elif self.on_surface["left"] or self.on_surface["right"]:
            self._on_wall_contact()

    def handle_collisions(self, axis):
        for sprite in pygame.sprite.spritecollide(self, self.collision_sprites, False, _hitbox_collide):
            if sprite is None or not hasattr(sprite, "rect") or sprite.rect is None:
                continue

            sprite_old = getattr(sprite, "old_rect", sprite.rect)
            is_moving_platform = hasattr(sprite, "old_rect")

            if axis == "horizontal":
                if self.old_rect.right <= sprite_old.left:
                    self.hitbox.right = sprite.rect.left
                elif self.old_rect.left >= sprite_old.right:
                    self.hitbox.left = sprite.rect.right
                if not is_moving_platform:
                    self.velocity.x = 0
            elif axis == "vertical":
                if self.old_rect.bottom <= sprite_old.top:
                    self.hitbox.bottom = sprite.rect.top
                elif self.old_rect.top >= sprite_old.bottom:
                    self.hitbox.top = sprite.rect.bottom
                self.velocity.y = 0

        self.sync_rects()

    def apply_moving_platform(self, moving_platforms):
        if not self.on_surface["floor"]:
            return
        for platform in moving_platforms:
            vertical_dist = self.hitbox.bottom - platform.old_rect.top
            if not (-2 <= vertical_dist <= 16):
                continue
            overlap = min(self.hitbox.right, platform.old_rect.right) - max(
                self.hitbox.left, platform.old_rect.left
            )
            if overlap <= 0:
                continue
            self.hitbox.x += platform.rect.x - platform.old_rect.x
            self.hitbox.y += platform.rect.y - platform.old_rect.y
            self.sync_rects()
            break

    def reset_position(self):
        self.hitbox.center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        self.sync_rects()
        self.velocity = Vector2(0, 0)
        self.old_rect = self.hitbox.copy()

    def update(self, delta_time):
        self.old_rect = self.hitbox.copy()