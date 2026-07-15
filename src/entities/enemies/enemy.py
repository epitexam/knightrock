from collections.abc import Sequence
from typing import Any

import pygame
import random
from pygame.sprite import Group

from src.combat.combat_component import CombatComponent
from src.combat.attack_loading import load_attacks
from src.entities.enemies.configs import ENEMY_CONFIGS
from src.entities.enemies.schema import EnemyConfig
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
from src.physics import lerp_velocity
from src.core.settings import Combat as CombatSettings


class Enemy(Entity):
    """Enemy entity configured by data instead of per-enemy boilerplate."""

    def __init__(
        self,
        pos: Sequence[float],
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        player_reference: Any,
        config: EnemyConfig,
    ) -> None:
        """Initialize an enemy from its configuration."""
        max_health = (
            config.max_health if config.max_health is not None else config.health
        )
        super().__init__(
            pos=pos,
            size=config.size,
            color=config.color,
            groups=groups,
            collision_sprites=collision_sprites,
            hitbox_inflate=config.hitbox_inflate,
            health=config.health,
            max_health=max_health,
            faction="enemy",
            spawn_pos=pos,
            combat=None,
        )

        self.config = config
        self.combat = CombatComponent(
            self,
            combo_window=CombatSettings.COMBO_WINDOW,
            hurt_duration=CombatSettings.HURT_DURATION,
        )
        load_attacks(self.combat, config.attacks)

        self.player = player_reference
        self.chase_speed = config.chase_speed
        self.vision_range = config.vision_range
        self.attack_range = config.attack_range
        self.attack_name = config.attack_name
        self.idle_duration = config.idle_duration
        self.passive_friction = config.passive_friction

        self.patrol_direction = 1 if random.random() > 0.5 else -1
        self.patrol_timer = 0.0
        self.patrol_interval = config.patrol_interval

        self.pushable = config.pushable
        self.super_armor = config.super_armor

        if config.has_ai:
            self._setup_state_machine()

    def _setup_state_machine(self) -> None:
        """Create the shared melee enemy state machine."""
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

    def update(self, delta_time: float) -> None:
        """Update the current state."""
        if self.is_dead:
            return
        super().update(delta_time)
        self.combat.update(delta_time)
        if self.config.has_ai:
            self.state_machine.update(delta_time)
        elif self.on_surface["floor"]:
            lerp_velocity(self, 0.0, min(
                1.0, self.passive_friction * delta_time), delta_time)

        self.move(delta_time, apply_gravity=True)

    def can_see_player(self) -> bool:
        """Return whether see player."""
        if self.player is None:
            return False
        return (
            pygame.math.Vector2(self.hitbox.center).distance_to(
                pygame.math.Vector2(self.player.hitbox.center)
            )
            < self.vision_range
        )

    def is_player_in_range(self) -> bool:
        """Return whether player in range."""
        if self.player is None:
            return False
        return (
            pygame.math.Vector2(self.hitbox.center).distance_to(
                pygame.math.Vector2(self.player.hitbox.center)
            )
            < self.attack_range
        )


class Goblin(Enemy):
    """Represent an enemy goblin with simple AI behavior."""

    def __init__(
        self,
        pos: Sequence[float],
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        player_reference: Any,
    ) -> None:
        """Initialize the Goblin instance."""
        super().__init__(
            pos=pos,
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_reference,
            config=ENEMY_CONFIGS["goblin"],
        )


class TrainingDummy(Enemy):
    """Represent a non-aggressive training target."""

    def __init__(
        self,
        pos: Sequence[float],
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        player_reference: Any = None,
    ) -> None:
        super().__init__(
            pos=pos,
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_reference,
            config=ENEMY_CONFIGS["dummy"],
        )
