from typing import TYPE_CHECKING

from state_machine import State

if TYPE_CHECKING:
    from player import Player


class PlayerIdleState(State["Player"]):
    def enter(self) -> None:
        self.entity.velocity.x = 0

    def update(self, delta_time: float) -> str | None:
        if self.entity.combat.is_attacking:
            return "attack"

        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"

        if not self.entity.on_surface["floor"]:
            return "fall"

        if self.entity.left_held or self.entity.right_held:
            return "run"

        return None


class PlayerRunState(State["Player"]):
    def update(self, delta_time: float) -> str | None:
        if self.entity.combat.is_attacking:
            return "attack"

        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"

        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity.on_surface["floor"]:
            return "fall"

        if self.entity.velocity.x == 0 and not (
            self.entity.left_held or self.entity.right_held
        ):
            return "idle"

        return None


class PlayerJumpState(State["Player"]):
    """State when the player gains altitude."""

    def update(self, delta_time: float) -> str | None:
        if self.entity.combat.is_attacking:
            return "attack"

        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.velocity.y >= 0:
            return "fall"

        if self.entity._is_wall_sliding():
            return "wall_slide"

        return None


class PlayerFallState(State["Player"]):
    """State when the player loses altitude."""

    def update(self, delta_time: float) -> str | None:
        if self.entity.combat.is_attacking:
            return "attack"

        self.entity.handle_jump()
        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.velocity.y < 0:
            return "jump"

        if self.entity._is_wall_sliding():
            return "wall_slide"

        if self.entity.on_surface["floor"]:
            if self.entity.left_held or self.entity.right_held:
                return "run"
            return "idle"

        return None


class PlayerWallSlideState(State["Player"]):
    """State when the player slides against a wall."""

    def update(self, delta_time: float) -> str | None:
        if self.entity.combat.is_attacking:
            return "attack"

        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"

        self.entity.apply_horizontal_movement(delta_time)

        if not self.entity._is_wall_sliding():
            return "fall"

        if self.entity.on_surface["floor"]:
            return "idle"

        return None


class PlayerAttackState(State["Player"]):
    def enter(self) -> None:
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x *= 0.1

    def update(self, delta_time: float) -> str | None:
        if not self.entity.combat.is_attacking:
            if self.entity.on_surface["floor"]:
                return "idle"
            return "fall"

        return None
