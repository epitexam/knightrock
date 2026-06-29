from typing import Optional
import pygame
import random

from src.combat.combat import CombatComponent
from src.states.enemy_states import (
    EnemyAttackState,
    EnemyChaseState,
    EnemyHurtState,
    EnemyIdleState,
    EnemyPatrolState,
    EnemyStaggerState,
)
from src.entities.entity import Entity
from src.states.state_machine import StateMachine
from src.combat.attack_data import GOBLIN_ATTACKS


class Goblin(Entity):
    def __init__(self, pos, groups, collision_sprites, player_reference):

        super().__init__(
            pos,
            (48, 48),
            (200, 50, 50),
            groups,
            collision_sprites,
            health=50.0,
            max_health=50.0,
            faction="enemy",
            spawn_pos=pos,
            combat=None,
        )
        self.combat = CombatComponent(self)
        for name, sequence in GOBLIN_ATTACKS.items():
            self.combat.add_attack(name, sequence)

        self.player = player_reference
        self.facing_right = True
        self.chase_speed = 120.0

        self.patrol_direction = 1 if random.random() > 0.5 else -1
        self.patrol_timer = 0.0
        self.patrol_interval = 2.0

        self.super_armor = False

        self.state_machine = StateMachine(self)
        self.state_machine.add_state("idle", EnemyIdleState(self))
        self.state_machine.add_state("patrol", EnemyPatrolState(self))
        self.state_machine.add_state("chase", EnemyChaseState(self))
        self.state_machine.add_state("attack", EnemyAttackState(self))
        self.state_machine.add_state("hurt", EnemyHurtState(self))
        self.state_machine.add_state("stagger", EnemyStaggerState(self))
        self.state_machine.set_initial_state("idle")

        self.state_machine.add_interrupt(
            "hurt",
            lambda: self.combat.is_hurt,
            priority=100,
        )

    def stagger(self, duration: float) -> None:
        if self.stagger_timer > 0:
            return
        super().stagger(duration)

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
