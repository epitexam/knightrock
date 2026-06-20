import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from settings import Display, Physics
from state_machine import StateMachine


def _hitbox_collide(a: Sprite, b: Sprite) -> bool:
    """
    Collision callback helper that prioritizes entity hitboxes over standard rects.
    """
    box_a = getattr(a, "hitbox", a.rect)
    box_b = getattr(b, "hitbox", b.rect)
    if isinstance(box_a, (pygame.FRect, pygame.Rect)) and isinstance(
        box_b, (pygame.FRect, pygame.Rect)
    ):
        return box_a.colliderect(box_b)
    return False


class Entity(Sprite):
    """
    Base class representing any dynamic or physical game object.
    Handles movement, sweeping AABB collisions, and environmental contact state.
    """

    hitbox: pygame.FRect
    old_rect: pygame.FRect
    collision_sprites: Group
    on_surface: Dict[str, bool]
    velocity: Vector2
    normal_gravity: float
    slide_gravity: float
    max_slide_speed: float

    def __init__(
        self,
        pos: Sequence[float] | Vector2,
        size: Sequence[float],
        color: Sequence[int],
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        hitbox_inflate: Sequence[float] = (0.0, 0.0),
    ) -> None:
        Sprite.__init__(self, groups)
        self.id: str = uuid.uuid4().hex
        self.pushable: bool = True

        self.image = pygame.Surface(size)  # type: ignore
        self.image.fill(color)  # type: ignore

        self.rect = self.image.get_frect(topleft=pos)
        self.hitbox = self.rect.inflate(*hitbox_inflate)
        self.hitbox.midbottom = self.rect.midbottom
        self.old_rect = self.hitbox.copy()

        self.collision_sprites = collision_sprites
        self.on_surface = {
            "floor": False,
            "left": False,
            "right": False,
        }
        self.velocity = Vector2(0, 0)

        self.normal_gravity = Physics.GRAVITY
        self.slide_gravity = Physics.GRAVITY * 0.15
        self.max_slide_speed = 80.0

        self.state_machine: Optional[StateMachine] = None

    @property
    def hurtbox(self) -> pygame.FRect:
        """Returns the active vulnerable area of the entity."""
        return self.hitbox

    def sync_rects(self) -> None:
        """Rescales or shifts cosmetic boundaries to match updated physical positions."""
        if self.rect is not None:
            self.rect.midbottom = self.hitbox.midbottom

    def _is_wall_sliding(self) -> bool:
        return False

    def _on_floor_contact(self) -> None:
        pass

    def _on_wall_contact(self) -> None:
        pass

    def apply_gravity(self, delta_time: float) -> None:
        if self._is_wall_sliding():
            self.velocity.y += self.slide_gravity * delta_time
            if self.velocity.y > self.max_slide_speed:
                self.velocity.y = self.max_slide_speed
        else:
            self.velocity.y += self.normal_gravity * delta_time

    def check_contact(self) -> None:
        height_quarter: float = self.hitbox.height / 4
        half_height: float = self.hitbox.height / 2

        floor_rect: pygame.FRect = pygame.FRect(
            self.hitbox.bottomleft, (self.hitbox.width, 2)
        )
        right_rect: pygame.FRect = pygame.FRect(
            self.hitbox.topright + Vector2(0, height_quarter), (2, half_height)
        )
        left_rect: pygame.FRect = pygame.FRect(
            self.hitbox.topleft + Vector2(-2, height_quarter), (2, half_height)
        )

        collide_rects: List[pygame.Rect | pygame.FRect] = [
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

    def handle_collisions(self, axis: str) -> None:
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

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        """Calculates and applies relative coordinate offsets when riding moving platforms."""
        if not self.on_surface["floor"]:
            return

        for platform in moving_platforms:
            if not hasattr(platform, "old_rect") or platform.old_rect is None:
                continue
            if not hasattr(platform, "rect") or platform.rect is None:
                continue

            vertical_dist: float = self.hitbox.bottom - platform.old_rect.top
            if not (-2 <= vertical_dist <= 16):
                continue

            overlap: float = min(self.hitbox.right, platform.old_rect.right) - max(
                self.hitbox.left, platform.old_rect.left
            )
            if overlap <= 0:
                continue

            platform_dx: float = platform.rect.x - platform.old_rect.x
            platform_dy: float = platform.rect.y - platform.old_rect.y

            self.hitbox.x += platform_dx
            self.hitbox.y += platform_dy
            self.sync_rects()
            break

    def reset_position(self) -> None:
        """Teleports the entity back to the display center and zeroes out momentum vectors."""
        self.hitbox.center = (Display.WIDTH // 2, Display.HEIGHT // 2)
        self.sync_rects()
        self.velocity = Vector2(0, 0)
        self.old_rect = self.hitbox.copy()

    def update(self, delta_time: float) -> None:
        """Updates internal frame-history boundaries required for accurate collision resolution."""
        self.old_rect = self.hitbox.copy()
