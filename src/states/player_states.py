from typing import Optional

import pygame

from src.states.state_machine import State
from src.core.settings import Combat as CombatSettings


class PlayerBaseState(State):
    def __init__(self, entity):
        super().__init__(entity)

    def ground_return(self) -> str:
        if self.entity.on_surface["floor"]:
            return (
                "run" if (self.entity.left_held or self.entity.right_held) else "idle"
            )
        return "fall"


class PlayerIdleState(PlayerBaseState):
    def enter(self, previous: Optional[str] = None) -> None:
        self.entity.velocity.x = 0

    def update(self, delta_time: float) -> Optional[str]:
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        if not self.entity.on_surface["floor"]:
            return "fall"
        if self.entity.left_held or self.entity.right_held:
            return "run"
        return None


class PlayerRunState(PlayerBaseState):
    def update(self, delta_time: float) -> Optional[str]:
        self.entity.apply_horizontal_movement(delta_time)
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        if not self.entity.on_surface["floor"]:
            return "fall"
        if (
            not (self.entity.left_held or self.entity.right_held)
            and abs(self.entity.velocity.x) < 0.1
        ):
            return "idle"
        return None


class PlayerJumpState(PlayerBaseState):
    def update(self, delta_time: float) -> Optional[str]:
        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)
        if self.entity.velocity.y >= 0:
            return "fall"
        if self.entity._is_wall_sliding():
            return "wall_slide"
        return None


class PlayerFallState(PlayerBaseState):
    def update(self, delta_time: float) -> Optional[str]:
        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)
        if self.entity.velocity.y < 0:
            return "jump"
        if self.entity._is_wall_sliding():
            return "wall_slide"
        return self.ground_return()


class PlayerWallSlideState(PlayerBaseState):
    def update(self, delta_time: float) -> Optional[str]:
        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"
        self.entity.apply_horizontal_movement(delta_time)
        if self.entity.on_surface["floor"]:
            return "idle"
        if not self.entity._is_wall_sliding():
            return "fall"
        return None


class PlayerAttackState(PlayerBaseState):
    def enter(self, previous: Optional[str] = None) -> None:
        if self.entity.on_surface["floor"]:
            direction = 1.0 if self.entity.facing_right else -1.0
            self.entity.velocity.x = direction * self.entity.speed * 0.35

    def update(self, delta_time: float) -> Optional[str]:
        if not self.entity.combat.is_attacking:
            return self.ground_return()
        return None


class PlayerBlockState(PlayerBaseState):
    def enter(self, previous: Optional[str] = None) -> None:
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x = 0
        old_bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height -= CombatSettings.BLOCK_HEIGHT_REDUCTION
        self.entity.hitbox.bottom = old_bottom
        self.entity.sync_rects()

    def exit(self, next_state: Optional[str] = None) -> None:
        if self.entity.block_stamina <= 0:
            self.entity.block_cooldown_timer = CombatSettings.BLOCK_COOLDOWN_BROKEN
        else:
            self.entity.block_cooldown_timer = CombatSettings.BLOCK_COOLDOWN_NORMAL
        old_bottom = self.entity.hitbox.bottom
        self.entity.hitbox.height += CombatSettings.BLOCK_HEIGHT_REDUCTION
        self.entity.hitbox.bottom = old_bottom
        self.entity.handle_collisions("vertical")
        self.entity.sync_rects()

    def update(self, delta_time: float) -> Optional[str]:
        self.entity.velocity.x = 0.0
        self.entity.block_stamina -= (
            delta_time if self.entity.on_surface["floor"] else delta_time * 2.0
        )
        if not self.entity.block_held or self.entity.block_stamina <= 0:
            return self.ground_return()
        return None


class PlayerHurtState(PlayerBaseState):
    def enter(self, previous: Optional[str] = None) -> None:
        self.entity._dash_requested = False

    def update(self, delta_time: float) -> Optional[str]:
        control = (
            self.entity.floor_control
            if self.entity.on_surface["floor"]
            else self.entity.air_control
        )
        self.entity.velocity.x = pygame.math.lerp(
            self.entity.velocity.x, 0.0, min(1.0, control * delta_time)
        )
        if not self.entity.combat.is_hurt:
            return self.ground_return()
        return None


class PlayerDashState(PlayerBaseState):
    def enter(self, previous: Optional[str] = None) -> None:
        self.entity.dash_charges -= 1
        self.entity._dash_requested = False
        if self.entity.dash_charges == 0:
            self.entity.dash_penalty_timer = self.entity.dash_penalty_duration
        self.entity._original_hitbox_width = self.entity.hitbox.width
        new_width = self.entity._original_hitbox_width * 0.6
        self.entity.hitbox.x += (self.entity._original_hitbox_width - new_width) / 2
        self.entity.hitbox.width = new_width
        direction = 1 if self.entity.facing_right else -1
        self.entity.velocity.x = self.entity.dash_speed * direction
        self.entity.velocity.y = 0.0
        self.entity._dash_duration_timer = self.entity.dash_duration

    def exit(self, next_state: Optional[str] = None) -> None:
        if hasattr(self.entity, "_original_hitbox_width"):
            current = self.entity.hitbox.width
            if current != self.entity._original_hitbox_width:
                self.entity.hitbox.x -= (
                    self.entity._original_hitbox_width - current
                ) / 2
                self.entity.hitbox.width = self.entity._original_hitbox_width
                self.entity.handle_collisions("horizontal")
                self.entity.sync_rects()

    def update(self, delta_time: float) -> Optional[str]:
        self.entity._dash_duration_timer -= delta_time
        friction = max(0.0, 1.0 - self.entity.dash_friction * delta_time)
        self.entity.velocity.x *= friction
        if self.entity.left_held:
            self.entity.velocity.x -= 100.0 * delta_time
        if self.entity.right_held:
            self.entity.velocity.x += 100.0 * delta_time
        self.entity.velocity.y = 0.0
        if self.entity._dash_duration_timer <= 0 or abs(self.entity.velocity.x) < 10.0:
            self.entity.velocity.x = 0.0
            return self.ground_return()
        return None