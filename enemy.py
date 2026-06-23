from typing import Optional

import pygame

from combat import AttackData, CombatComponent
from enemy_states import (
    EnemyAttackState,
    EnemyChaseState,
    EnemyHurtState,
    EnemyPatrolState,
)
from entity import Entity
from state_machine import StateMachine


class Goblin(Entity):
    def __init__(self, pos, groups, collision_sprites, player_reference):
        super().__init__(pos, (48, 48), (200, 50, 50), groups, collision_sprites)
        self.player = player_reference
        self.facing_right = True
        self.chase_speed = 120.0

        self.combat = CombatComponent(self)
        self.combat.add_attack(
            "claw_swipe",
            AttackData(
                size=(50, 30),
                offset=(25, -5),
                damage=10,
                duration=0.2,
                cooldown=1.0,
            ),
        )

        self.state_machine = StateMachine(self)
        self.state_machine.add_state("patrol", EnemyPatrolState(self))
        self.state_machine.add_state("chase", EnemyChaseState(self))
        self.state_machine.add_state("attack", EnemyAttackState(self))
        self.state_machine.add_state("hurt", EnemyHurtState(self))
        self.state_machine.set_initial_state("patrol")

        self.state_machine.add_interrupt(
            "hurt",
            lambda: self.combat.is_hurt,
            priority=100,
        )

    def update(self, delta_time: float) -> None:
        super().update(delta_time) 
        self.combat.update(delta_time, self.facing_right)
        if self.state_machine is not None:
            self.state_machine.update(delta_time)

        self.move(delta_time, apply_gravity=True)

    def can_see_player(self) -> bool:
        if self.player is None:
            return False
        return (
            pygame.math.Vector2(self.hitbox.center).distance_to(
                pygame.math.Vector2(self.player.hitbox.center)
            )
            < 300.0
        )

    def is_player_in_range(self) -> bool:
        if self.player is None:
            return False
        return (
            pygame.math.Vector2(self.hitbox.center).distance_to(
                pygame.math.Vector2(self.player.hitbox.center)
            )
            < 60.0
        )
