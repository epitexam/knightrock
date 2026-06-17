import pygame
from pygame.math import Vector2

from settings import GRAVITY, WINDOW_HEIGHT, WINDOW_WIDTH


def _hitbox_collide(a, b):
    """
    Collision callback helper that prioritizes entity hitboxes over standard rects.
    """
    box_a = getattr(a, "hitbox", a.rect)
    box_b = getattr(b, "hitbox", b.rect)
    return box_a.colliderect(box_b)


class Entity(pygame.sprite.Sprite):
    """
    Base class representing any dynamic or physical game object.
    Handles movement, sweeping AABB collisions, and environmental contact state.
    """

    def __init__(
        self, pos, size, color, groups, collision_sprites, hitbox_inflate=(0, 0)
    ):
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
        """Returns the active vulnerable area of the entity."""
        return self.hitbox

    def sync_rects(self):
        """Synchronizes the visual rendering rect position with the underlying physics hitbox."""
        self.rect.midbottom = self.hitbox.midbottom

    def _is_wall_sliding(self) -> bool:
        """Virtual method designed to be overridden by subclasses to detect wall sliding."""
        return False

    def _on_floor_contact(self):
        """Virtual callback executed instantly when the entity lands on a floor."""
        pass

    def _on_wall_contact(self):
        """Virtual callback executed instantly when the entity touches a vertical wall."""
        pass

    def apply_gravity(self, delta_time):
        """Applies downward acceleration, handling reduced terminal velocity if wall sliding."""
        if self._is_wall_sliding():
            self.velocity.y += self.slide_gravity * delta_time
            if self.velocity.y > self.max_slide_speed:
                self.velocity.y = self.max_slide_speed
        else:
            self.velocity.y += self.normal_gravity * delta_time

    def check_contact(self):
        """Generates low-profile sensory sub-rectangles to accurately probe solid surface contacts."""
        height_quarter = self.hitbox.height / 4
        half_height = self.hitbox.height / 2

        floor_rect = pygame.FRect(self.hitbox.bottomleft, (self.hitbox.width, 2))
        right_rect = pygame.FRect(
            self.hitbox.topright + Vector2(0, height_quarter), (2, half_height)
        )
        left_rect = pygame.FRect(
            self.hitbox.topleft + Vector2(-2, height_quarter), (2, half_height)
        )

        collide_rects = [
            s.rect
            for s in self.collision_sprites
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
        """Resolves collisions along a specified vector axis and halts velocity upon impact."""
        for sprite in pygame.sprite.spritecollide(
            self, self.collision_sprites, False, _hitbox_collide
        ):
            if sprite is None or not hasattr(sprite, "rect") or sprite.rect is None:
                continue

            sprite_old = getattr(sprite, "old_rect", sprite.rect)

            if axis == "horizontal":
                if self.old_rect.right <= sprite_old.left:
                    self.hitbox.right = sprite.rect.left
                elif self.old_rect.left >= sprite_old.right:
                    self.hitbox.left = sprite.rect.right
                self.velocity.x = 0
            elif axis == "vertical":
                if self.old_rect.bottom <= sprite_old.top:
                    self.hitbox.bottom = sprite.rect.top
                elif self.old_rect.top >= sprite_old.bottom:
                    self.hitbox.top = sprite.rect.bottom
                self.velocity.y = 0

        self.sync_rects()

    def apply_moving_platform(self, moving_platforms):
        """Calculates and applies relative coordinate offsets when riding moving platforms."""
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

            platform_dx = platform.rect.x - platform.old_rect.x
            platform_dy = platform.rect.y - platform.old_rect.y

            self.hitbox.x += platform_dx
            self.hitbox.y += platform_dy
            self.sync_rects()
            break

    def reset_position(self):
        """Teleports the entity back to the display center and zeroes out momentum vectors."""
        self.hitbox.center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        self.sync_rects()
        self.velocity = Vector2(0, 0)
        self.old_rect = self.hitbox.copy()

    def update(self, delta_time):
        """Updates internal frame-history boundaries required for accurate collision resolution."""
        self.old_rect = self.hitbox.copy()
