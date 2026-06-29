import math
import uuid
from typing import Any, Iterable, Sequence, Union

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from src.core.settings import Physics, Separation, Combat as CombatSettings
from src.combat.attack_types import KnockbackConfig
from src.combat.combat import NullCombatComponent, CombatComponent


def _hitbox_collide(a: Sprite, b: Sprite) -> bool:
    box_a = getattr(a, "hitbox", a.rect)
    box_b = getattr(b, "hitbox", b.rect)
    if isinstance(box_a, (pygame.FRect, pygame.Rect)) and isinstance(
        box_b, (pygame.FRect, pygame.Rect)
    ):
        return box_a.colliderect(box_b)
    return False


class Entity(Sprite):
    hitbox: pygame.FRect
    old_hitbox: pygame.FRect
    collision_sprites: Group
    on_surface: dict[str, bool]
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
        health: float = 100.0,
        max_health: float = 100.0,
        faction: str = "neutral",
        spawn_pos: Sequence[float] | Vector2 | None = None,
        combat: CombatComponent | None = None,
    ) -> None:
        Sprite.__init__(self, groups)
        self.id: str = uuid.uuid4().hex
        self.pushable: bool = True
        self.faction: str = faction

        self.image = pygame.Surface(size)
        self.image.fill(color)

        self.rect = self.image.get_frect(topleft=pos)
        self.hitbox = self.rect.inflate(*hitbox_inflate)
        self.hitbox.midbottom = self.rect.midbottom
        self.old_hitbox = self.hitbox.copy()

        self.collision_sprites = collision_sprites
        self.on_surface = {"floor": False, "left": False, "right": False}
        self.velocity = Vector2(0, 0)

        self.normal_gravity = Physics.GRAVITY
        self.slide_gravity = Physics.GRAVITY * 0.15
        self.max_slide_speed = 80.0

        self._health = health
        self._max_health = max_health
        self.is_dead = False

        if spawn_pos is None:
            spawn_pos = pos
        self.spawn_pos = Vector2(spawn_pos)

        self.combat: CombatComponent | NullCombatComponent = (
            combat or NullCombatComponent()
        )
        self.facing_right = True

        self.stagger_timer = 0.0
        self.super_armor = False
        self.super_armor_count = 0

    @property
    def health(self) -> float:
        return self._health

    @health.setter
    def health(self, value: float) -> None:
        old = self._health
        self._health = max(0.0, min(value, self._max_health))
        if old > 0 and self._health == 0 and not self.is_dead:
            self.die()

    @property
    def max_health(self) -> float:
        return self._max_health

    @max_health.setter
    def max_health(self, value: float) -> None:
        self._max_health = max(1.0, value)

    def die(self) -> None:
        self.is_dead = True

    @property
    def hurtbox(self) -> pygame.FRect:
        return self.hitbox

    def sync_rects(self) -> None:
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
        height_quarter = self.hitbox.height / 4
        half_height = self.hitbox.height / 2

        floor_rect = pygame.FRect(
            self.hitbox.bottomleft, (self.hitbox.width, 2))
        right_rect = pygame.FRect(
            Vector2(self.hitbox.topright) +
            Vector2(0, height_quarter), (2, half_height)
        )
        left_rect = pygame.FRect(
            Vector2(self.hitbox.topleft) + Vector2(-2,
                                                   height_quarter), (2, half_height)
        )

        self.on_surface["floor"] = False
        self.on_surface["right"] = False
        self.on_surface["left"] = False

        for sprite in self.collision_sprites:
            box = getattr(sprite, "hitbox", getattr(sprite, "rect", None))
            if box is None:
                continue
            if floor_rect.colliderect(box):
                self.on_surface["floor"] = True
            if right_rect.colliderect(box):
                self.on_surface["right"] = True
            if left_rect.colliderect(box):
                self.on_surface["left"] = True

            if (
                self.on_surface["floor"]
                and self.on_surface["right"]
                and self.on_surface["left"]
            ):
                break

        if self.on_surface["floor"]:
            self._on_floor_contact()
        elif self.on_surface["left"] or self.on_surface["right"]:
            self._on_wall_contact()

    def handle_collisions(self, axis: str) -> None:
        search_area = self.hitbox.inflate(
            Separation.SEARCH_INFLATE, Separation.SEARCH_INFLATE
        )

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
        move_x = self.velocity.x * delta_time
        steps_x = max(1, math.ceil(abs(move_x) / Separation.SUB_STEP_SIZE))
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
        steps_y = max(1, math.ceil(abs(move_y) / Separation.SUB_STEP_SIZE))
        step_move_y = move_y / steps_y

        for _ in range(steps_y):
            self.old_hitbox = self.hitbox.copy()
            self.hitbox.y += step_move_y
            self.handle_collisions("vertical")
            if self.velocity.y == 0:
                break

        self.check_contact()

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        if not self.on_surface["floor"]:
            return

        for platform in moving_platforms:
            p_box = getattr(platform, "hitbox",
                            getattr(platform, "rect", None))
            p_old_box = getattr(
                platform, "old_hitbox", getattr(platform, "old_rect", None)
            )

            if p_box is None or p_old_box is None:
                continue

            vertical_dist = self.hitbox.bottom - p_old_box.top
            if not (-2 <= vertical_dist <= 16):
                continue

            overlap = min(self.hitbox.right, p_old_box.right) - max(
                self.hitbox.left, p_old_box.left
            )
            if overlap <= 0:
                continue

            platform_dx = p_box.x - p_old_box.x
            platform_dy = p_box.y - p_old_box.y

            self.hitbox.x += platform_dx
            self.hitbox.y += platform_dy
            self.sync_rects()
            break

    def reset_position(self) -> None:
        self.hitbox.center = self.spawn_pos
        self.sync_rects()
        self.velocity = Vector2(0, 0)
        self.old_hitbox = self.hitbox.copy()
        self.is_dead = False
        self.stagger_timer = 0.0
        self.super_armor = False
        self.super_armor_count = 0

    def receive_damage(
        self,
        amount: int,
        source_center_x: float | None = None,
        knockback: KnockbackConfig | None = None,
    ) -> None:
        _kb = knockback if knockback is not None else KnockbackConfig()

        self.health -= amount

        if self.combat is not None:
            hurt_duration = (
                CombatSettings.HURT_DURATION
                + abs(_kb.power[1]) *
                CombatSettings.HURT_DURATION_KNOCKBACK_SCALE
            )
            self.combat.on_hit(hurt_duration)

        if _kb.mode == "fixed":
            self.velocity.x = _kb.power[0]
            self.velocity.y = _kb.power[1]
        else:
            if source_center_x is not None:
                direction = 1.0 if self.hitbox.centerx >= source_center_x else -1.0
            else:
                direction = 1.0 if getattr(
                    self, "facing_right", True) else -1.0
            self.velocity.x = _kb.power[0] * direction
            self.velocity.y = _kb.power[1]

    def stagger(self, duration: float) -> None:
        """Apply stagger effect, considering super armor."""
        if self.super_armor:
            self.super_armor_count += 1
            if self.super_armor_count >= CombatSettings.SUPER_ARMOR_THRESHOLD:
                self.super_armor = False
                self.stagger_timer = duration
                if hasattr(self, 'state_machine') and self.state_machine:
                    self.state_machine.change_state("stagger")
        else:
            self.stagger_timer = duration
            if hasattr(self, 'state_machine') and self.state_machine:
                self.state_machine.change_state("stagger")

    def update(self, delta_time: float) -> None:
        self.old_hitbox = self.hitbox.copy()
        if self.stagger_timer > 0:
            self.stagger_timer -= delta_time
            if self.stagger_timer < 0:
                self.stagger_timer = 0.0
