"""Enemy entities configured by data with AI state machines and combat capabilities."""

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
from src.physics import lerp_velocity, apply_horizontal_movement
from src.core.settings import Combat as CombatSettings


class Enemy(Entity):
    """Enemy entity configured by data instead of per-enemy boilerplate.

    Attributes
    ----------
    config : EnemyConfig
        Data class holding enemy parameters.
    player : Any
        Reference to the player entity for AI targeting.
    chase_speed : float
        Movement speed when chasing the player.
    vision_range : float
        Distance at which the enemy can detect the player.
    attack_range : float
        Distance required to initiate an attack.
    attack_name : str
        Name of the attack definition loaded into the combat component.
    idle_duration : float
        Time spent in the idle state before patrolling.
    passive_friction : float
        Friction applied when the enemy has no AI.
    move_axis : float
        Normalized horizontal input for physics calculations.
    speed : float
        Current maximum movement speed.
    floor_control : float
        Ground acceleration factor.
    air_control : float
        Air acceleration factor.
    patrol_direction : int
        1 for right, -1 for left.
    patrol_timer : float
        Time elapsed in current patrol direction.
    patrol_interval : float
        Time before changing patrol direction.
    pushable : bool
        Whether the entity can be pushed by separation system.
    super_armor : bool
        Whether the entity ignores stagger.
    """

    def __init__(
        self,
        pos: Sequence[float],
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        player_reference: Any,
        config: EnemyConfig,
    ) -> None:
        """Initialize an enemy from its configuration.

        Parameters
        ----------
        pos : Sequence[float]
            Starting top-left position.
        groups : Group | Sequence[Group]
            Sprite group(s) to add this enemy to.
        collision_sprites : Group
            Group of sprites that block movement.
        player_reference : Any
            Reference to the player entity.
        config : EnemyConfig
            Data class holding enemy parameters.
        """
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

        self.move_axis = 0.0
        self.speed = self.chase_speed
        self.floor_control = 20.0
        self.air_control = 10.0

        self.patrol_direction = 1 if random.random() > 0.5 else -1
        self.patrol_timer = 0.0
        self.patrol_interval = config.patrol_interval

        self.pushable = config.pushable
        self.super_armor = config.super_armor

        if self.player is not None:
            self.facing_right = self.player.hitbox.centerx > self.hitbox.centerx
        else:
            self.facing_right = True

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

    def face_player(self) -> None:
        """Orient the enemy toward the player if player exists.

        Includes a small threshold to prevent rapid toggling when
        horizontally aligned.
        """
        if self.player is None or self.is_dead:
            return

        if abs(self.player.hitbox.centerx - self.hitbox.centerx) > 2.0:
            self.facing_right = self.player.hitbox.centerx > self.hitbox.centerx

    def apply_horizontal_movement(self, delta_time: float) -> None:
        """Delegate to the shared physics function.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        """
        apply_horizontal_movement(self, delta_time)

    def update(self, delta_time: float) -> None:
        """Update the current state, direction, and combat.

        Ensures facing direction is resolved correctly before the combat
        component updates the attack hitbox position.

        Parameters
        ----------
        delta_time : float
            Elapsed time in seconds since the last frame.
        """
        if self.is_dead:
            return
        super().update(delta_time)

        if self.config.has_ai and self.player is not None:
            current = self.state_machine.current_state_name
            if current not in ("attack", "hurt", "stagger"):
                self.face_player()

        self.combat.update(delta_time)

        if self.config.has_ai:
            self.state_machine.update(delta_time)
        elif self.on_surface["floor"]:
            lerp_velocity(self, 0.0, min(
                1.0, self.passive_friction * delta_time), delta_time)

        self.move(delta_time, apply_gravity=True)

    def can_see_player(self) -> bool:
        """Check if the player is within vision range.

        Returns
        -------
        bool
            True if the player is close enough to be detected.
        """
        if self.player is None:
            return False
        return (
            pygame.math.Vector2(self.hitbox.center).distance_to(
                pygame.math.Vector2(self.player.hitbox.center)
            )
            < self.vision_range
        )

    def is_player_in_range(self) -> bool:
        """Check if the player is within attack range.

        Returns
        -------
        bool
            True if the player is close enough to be attacked.
        """
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
        """Initialize the Goblin instance.

        Parameters
        ----------
        pos : Sequence[float]
            Starting top-left position.
        groups : Group | Sequence[Group]
            Sprite group(s) to add this goblin to.
        collision_sprites : Group
            Group of sprites that block movement.
        player_reference : Any
            Reference to the player entity.
        """
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
        """Initialize the TrainingDummy instance.

        Parameters
        ----------
        pos : Sequence[float]
            Starting top-left position.
        groups : Group | Sequence[Group]
            Sprite group(s) to add this dummy to.
        collision_sprites : Group
            Group of sprites that block movement.
        player_reference : Any, optional
            Reference to the player entity.
        """
        super().__init__(
            pos=pos,
            groups=groups,
            collision_sprites=collision_sprites,
            player_reference=player_reference,
            config=ENEMY_CONFIGS["dummy"],
        )
