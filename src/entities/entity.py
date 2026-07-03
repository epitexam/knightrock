import uuid
from typing import Any, Iterable, Sequence

import pygame
from pygame.math import Vector2
from pygame.sprite import Group, Sprite

from src.core.settings import Physics, Combat as CombatSettings
from src.combat.attack_types import KnockbackConfig
from src.combat.combat import NullCombatComponent, CombatComponent
from src.combat.damage_types import DamageType
from src.physics import (
    apply_entity_gravity,
    apply_moving_platform,
    move_entity,
    resolve_collisions,
    update_contact_state,
)


class Entity(Sprite):
    """Represent a Entity."""
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
        """Initialize the Entity instance."""
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
        self.fall_gravity = Physics.FALL_GRAVITY
        self.slide_gravity = Physics.GRAVITY * 0.15
        self.max_slide_speed = 80.0
        self.max_fall_speed = Physics.MAX_FALL_SPEED

        self.drag_coefficient = 0.08
        self.fall_drag_coefficient = 0.12

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
        """Perform health."""
        return self._health

    @health.setter
    def health(self, value: float) -> None:
        """Perform health."""
        old = self._health
        self._health = max(0.0, min(value, self._max_health))
        if old > 0 and self._health == 0 and not self.is_dead:
            self.die()

    @property
    def max_health(self) -> float:
        """Perform max health."""
        return self._max_health

    @max_health.setter
    def max_health(self, value: float) -> None:
        """Perform max health."""
        self._max_health = max(1.0, value)

    def die(self) -> None:
        """Mark the entity as dead and perform cleanup."""
        self.is_dead = True

    @property
    def hurtbox(self) -> pygame.FRect:
        """Perform hurtbox."""
        return self.hitbox

    @property
    def has_super_armor(self) -> bool:
        return self.super_armor

    def break_super_armor(self) -> None:
        self.super_armor = False
        self.super_armor_count = 0

    def get_damage_modifier(self, damage_type: DamageType) -> float:
        return 1.0

    def sync_rects(self) -> None:
        """Sync rect and hitbox positions."""
        if self.rect is not None:
            self.rect.midbottom = self.hitbox.midbottom

    def _is_wall_sliding(self) -> bool:
        """Internal helper for is wall sliding."""
        return False

    def _on_floor_contact(self) -> None:
        """Internal helper for on floor contact."""
        pass

    def _on_wall_contact(self) -> None:
        """Internal helper for on wall contact."""
        pass

    def apply_gravity(self, delta_time: float) -> None:
        """Apply gravity."""
        apply_entity_gravity(self, delta_time)

    def check_contact(self) -> None:
        """Check contact."""
        update_contact_state(self, self.collision_sprites)

    def handle_collisions(self, axis: str) -> None:
        """Handle collisions."""
        resolve_collisions(self, axis)

    def move(self, delta_time: float, apply_gravity: bool = True) -> None:
        """Move the entity based on velocity and environment."""
        self.apply_moving_platform(getattr(self, "moving_platforms", []))
        move_entity(self, delta_time, apply_gravity=apply_gravity)

    def apply_moving_platform(self, moving_platforms: Iterable[Any]) -> None:
        """Apply moving platform."""
        apply_moving_platform(self, moving_platforms)

    def reset_position(self) -> None:
        """Reset position."""
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
        """Apply damage to this entity."""
        if self.is_dead:
            return

        self.health -= amount

        if knockback is not None:
            _kb = knockback
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

            if self.combat is not None:
                hurt_duration = (
                    CombatSettings.HURT_DURATION
                    + abs(_kb.power[1]) *
                    CombatSettings.HURT_DURATION_KNOCKBACK_SCALE
                )
                self.combat.on_hit(hurt_duration)

    def stagger(self, duration: float) -> None:
        """Apply stagger effect, considering super armor."""
        if self.is_dead:
            return
        if self.super_armor:
            self.super_armor_count += 1
            if self.super_armor_count >= CombatSettings.SUPER_ARMOR_THRESHOLD:
                self.super_armor = False
                self.stagger_timer = duration
                if hasattr(self, 'state_machine') and self.state_machine:
                    self.combat.is_hurt = False
                    self.combat.hurt_timer = 0.0
                    self.state_machine.change_state("stagger", force=True)
        else:
            self.stagger_timer = duration
            if hasattr(self, 'state_machine') and self.state_machine:
                self.combat.is_hurt = False
                self.combat.hurt_timer = 0.0
                self.state_machine.change_state("stagger", force=True)

    def update(self, delta_time: float) -> None:
        """Update the current state."""
        self.old_hitbox = self.hitbox.copy()
        if self.stagger_timer > 0:
            self.stagger_timer -= delta_time
            if self.stagger_timer < 0:
                self.stagger_timer = 0.0
