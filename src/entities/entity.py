import math
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from src.core.settings import Display, Physics
from src.states.state_machine import StateMachine


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
    old_hitbox: pygame.FRect
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
        self.old_hitbox = self.hitbox.copy()

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
        """Aligns the visual rect to the bottom of the physical hitbox (feet-anchored)."""
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
            Vector2(self.hitbox.topright) + Vector2(0, height_quarter), (2, half_height)
        )
        left_rect: pygame.FRect = pygame.FRect(
            Vector2(self.hitbox.topleft) + Vector2(-2, height_quarter), (2, half_height)
        )

        collide_rects: List[pygame.Rect | pygame.FRect] = [
            getattr(s, "hitbox", s.rect)
            for s in self.collision_sprites
            if s is not None and (hasattr(s, "hitbox") or hasattr(s, "rect"))
        ]

        self.on_surface["floor"] = floor_rect.collidelist(collide_rects) >= 0
        self.on_surface["right"] = right_rect.collidelist(collide_rects) >= 0
        self.on_surface["left"] = left_rect.collidelist(collide_rects) >= 0

        if self.on_surface["floor"]:
            self._on_floor_contact()
        elif self.on_surface["left"] or self.on_surface["right"]:
            self._on_wall_contact()

    def handle_collisions(self, axis: str) -> None:
        search_area = self.hitbox.inflate(400, 400)

        nearby_sprites = []
        for sprite in self.collision_sprites:
            box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
            if box is not None and search_area.colliderect(box):
                nearby_sprites.append(sprite)

        for sprite in nearby_sprites:
            if sprite is None or not hasattr(sprite, "rect") or sprite.rect is None:
                continue
            if not _hitbox_collide(self, sprite):
                continue

            sprite_old = getattr(
                sprite, "old_hitbox", getattr(sprite, "old_rect", sprite.rect)
            )
            sprite_box = getattr(sprite, "hitbox", sprite.rect)

            if axis == "horizontal":
                if self.old_hitbox.right <= sprite_old.left:
                    self.hitbox.right = sprite_box.left
                elif self.old_hitbox.left >= sprite_old.right:
                    self.hitbox.left = sprite_box.right
                else:
                    if abs(self.hitbox.right - sprite_box.left) < abs(
                        self.hitbox.left - sprite_box.right
                    ):
                        self.hitbox.right = sprite_box.left
                    else:
                        self.hitbox.left = sprite_box.right
                self.velocity.x = 0

            elif axis == "vertical":
                if self.old_hitbox.bottom <= sprite_old.top:
                    self.hitbox.bottom = sprite_box.top
                elif self.old_hitbox.top >= sprite_old.bottom:
                    self.hitbox.top = sprite_box.bottom
                else:
                    if abs(self.hitbox.bottom - sprite_box.top) < abs(
                        self.hitbox.top - sprite_box.bottom
                    ):
                        self.hitbox.bottom = sprite_box.top
                    else:
                        self.hitbox.top = sprite_box.bottom
                self.velocity.y = 0

        self.sync_rects()

    def move(self, delta_time: float, apply_gravity: bool = True) -> None:
        """Handles full physics resolution sequence with sub-stepping for any entity."""

        move_x = self.velocity.x * delta_time
        steps_x = max(1, math.ceil(abs(move_x) / 16.0))
        step_move_x = move_x / steps_x

        for _ in range(steps_x):
            self.old_hitbox = self.hitbox.copy()
            self.hitbox.x += step_move_x
            self.handle_collisions("horizontal")
            if self.velocity.x == 0:
                break

        if apply_gravity:
            self.apply_gravity(delta_time)

        move_y = self.velocity.y * delta_time
        steps_y = max(1, math.ceil(abs(move_y) / 16.0))
        step_move_y = move_y / steps_y

        for _ in range(steps_y):
            self.old_hitbox = self.hitbox.copy()
            self.hitbox.y += step_move_y
            self.handle_collisions("vertical")
            if self.velocity.y == 0:
                break

        self.check_contact()

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        """Calculates and applies relative coordinate offsets when riding moving platforms."""
        if not self.on_surface["floor"]:
            return

        for platform in moving_platforms:
            p_box = getattr(platform, "hitbox", getattr(platform, "rect", None))
            p_old_box = getattr(
                platform, "old_hitbox", getattr(platform, "old_rect", None)
            )

            if p_box is None or p_old_box is None:
                continue

            vertical_dist: float = self.hitbox.bottom - p_old_box.top
            if not (-2 <= vertical_dist <= 16):
                continue

            overlap: float = min(self.hitbox.right, p_old_box.right) - max(
                self.hitbox.left, p_old_box.left
            )
            if overlap <= 0:
                continue

            platform_dx: float = p_box.x - p_old_box.x
            platform_dy: float = p_box.y - p_old_box.y

            self.hitbox.x += platform_dx
            self.hitbox.y += platform_dy
            self.sync_rects()
            break

    def reset_position(self) -> None:
        """Teleports the entity back to the display center and zeroes out momentum vectors."""
        self.hitbox.center = (Display.WIDTH // 2, Display.HEIGHT // 2)
        self.sync_rects()
        self.velocity = Vector2(0, 0)
        self.old_hitbox = self.hitbox.copy()

    def update(self, delta_time: float) -> None:
        """Updates internal frame-history boundaries required for accurate collision resolution."""
        self.old_hitbox = self.hitbox.copy()
