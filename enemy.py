import pygame

from combat import CombatComponent
from entity import Entity
from state_machine import State, StateMachine


class EnemyHurtState(State):
    """State where the enemy takes a hit (stunned)."""

    def update(self, delta_time: float) -> str | None:
        if self.entity.on_surface["floor"]:
            self.entity.velocity.x = pygame.math.lerp(
                self.entity.velocity.x, 0.0, min(1.0, 10.0 * delta_time)
            )

        if not self.entity.combat.is_hurt:
            return "patrol"
        return None


class EnemyPatrolState(State):
    def enter(self) -> None:
        self.entity.velocity.x = 0.0

    def update(self, delta_time: float) -> str | None:
        if self.entity.combat.is_hurt:
            return "hurt"

        if self.entity.can_see_player():
            return "chase"
        return None


class EnemyChaseState(State):
    def update(self, delta_time: float) -> str | None:
        if self.entity.combat.is_hurt:
            return "hurt"

        if self.entity.is_player_in_range():
            return "attack"
        if not self.entity.can_see_player():
            return "patrol"
        return None


class Goblin(Entity):
    def __init__(self, pos, groups, collision_sprites, player_reference):
        super().__init__(pos, (48, 48), (200, 50, 50), groups, collision_sprites)
        self.player = player_reference

        self.combat = CombatComponent(self)

        self.state_machine = StateMachine(self)
        self.state_machine.add_state("patrol", EnemyPatrolState(self))
        self.state_machine.add_state("chase", EnemyChaseState(self))
        self.state_machine.add_state("hurt", EnemyHurtState(self))
        self.state_machine.set_initial_state("patrol")

    def update(self, delta_time: float) -> None:
        super().update(delta_time)

        self.combat.update(delta_time, facing_right=True)

        assert self.state_machine is not None
        self.state_machine.update(delta_time)

        self.apply_gravity(delta_time)
        self.hitbox.x += self.velocity.x * delta_time
        self.handle_collisions("horizontal")
        self.hitbox.y += self.velocity.y * delta_time
        self.handle_collisions("vertical")
        self.check_contact()

    def can_see_player(self) -> bool:
        return False

    def is_player_in_range(self) -> bool:
        return False
