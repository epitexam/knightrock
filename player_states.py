from typing import TYPE_CHECKING

from state_machine import State

if TYPE_CHECKING:
    from player import Player


class PlayerGroundedState(State["Player"]):
    """
    Classe parente pour les états au sol (Idle, Run).
    Centralise les transitions communes : block, attack, jump, fall.
    """

    def check_global_transitions(self) -> str | None:
        """Vérifie les transitions prioritaires communes à tous les états au sol."""
        if (
            self.entity.block_held
            and self.entity.block_cooldown_timer <= 0
            and self.entity.block_stamina > 0.3
        ):
            return "block"

        if self.entity.combat.is_attacking:
            return "attack"

        self.entity.handle_jump()
        if self.entity.velocity.y < 0:
            return "jump"

        # Fall
        if not self.entity.on_surface["floor"]:
            return "fall"

        return None


class PlayerIdleState(PlayerGroundedState):
    def enter(self) -> None:
        self.entity.velocity.x = 0

    def update(self, delta_time: float) -> str | None:
        transition = self.check_global_transitions()
        if transition:
            return transition

        if self.entity.left_held or self.entity.right_held:
            return "run"

        return None


class PlayerRunState(PlayerGroundedState):
    def update(self, delta_time: float) -> str | None:
        transition = self.check_global_transitions()
        if transition:
            return transition

        self.entity.apply_horizontal_movement(delta_time)

        is_moving = abs(self.entity.velocity.x) > 0.1
        input_active = self.entity.left_held or self.entity.right_held
        if not is_moving and not input_active:
            return "idle"

        return None


class PlayerJumpState(State["Player"]):
    """State when the player gains altitude."""

    def update(self, delta_time: float) -> str | None:
        if (
            self.entity.block_held
            and self.entity.block_cooldown_timer <= 0
            and self.entity.block_stamina > 0.3
        ):
            return "block"

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
        if (
            self.entity.block_held
            and self.entity.block_cooldown_timer <= 0
            and self.entity.block_stamina > 0.3
        ):
            return "block"

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


class PlayerBlockState(State["Player"]):
    """State when the player is blocking (holding LSHIFT)."""

    def enter(self) -> None:
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x = 0

    def exit(self) -> None:
        if self.entity.block_stamina <= 0:
            self.entity.block_cooldown_timer = 2.0
        else:
            self.entity.block_cooldown_timer = 0.5

    def update(self, delta_time: float) -> str | None:
        if self.entity.on_surface["floor"]:
            self.entity.block_stamina -= delta_time
        else:
            self.entity.block_stamina -= delta_time * 2.0

        if not self.entity.block_held or self.entity.block_stamina <= 0:
            if self.entity.on_surface["floor"]:
                return "idle"
            return "fall"

        return None
