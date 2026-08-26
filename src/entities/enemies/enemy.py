"""Enemy entities configured by data with AI state machines and combat capabilities."""

import random
from collections.abc import Sequence
from typing import Protocol

import pygame
from pygame.math import Vector2
from pygame.sprite import Group

from src.entities.enemies.schema import EnemyConfig
from src.states.enemy_states import (
    EnemyAttackState,
    EnemyChargeState,
    EnemyChaseState,
    EnemyHurtState,
    EnemyIdleState,
    EnemyKnockbackState,
    EnemyPatrolState,
    EnemyStaggerState,
)
from src.entities.entity import Entity
from src.states.state_machine import StateMachine
from src.physics import lerp_velocity
from src.core.settings import Combat as CombatSettings


class PlayerReference(Protocol):
    """Protocol for player reference to enable proper typing.

    This protocol defines the minimal interface that a player reference
    must provide for enemy AI to function correctly.
    """
    hitbox: pygame.FRect


class Enemy(Entity):
    """Enemy entity configured by data instead of per-enemy boilerplate.

    This class provides a data-driven approach to enemy creation, where all
    enemy parameters are defined in EnemyConfig dataclasses. This eliminates
    the need for individual enemy subclasses that only differ in their
    configuration.

    Attributes
    ----------
    config : EnemyConfig
        Data class holding enemy parameters.
    player : PlayerReference | None
        Reference to the player entity for AI targeting.
    chase_speed : float
        Movement speed when chasing the player.
    vision_range : float
        Distance at which the enemy can detect the player.
    attack_range : float
        Distance required to initiate an attack.
    attack_name : str | None
        Name of the attack definition loaded into the combat component.
    idle_duration : float
        Time spent in the idle state before patrolling.
    passive_friction : float
        Friction applied when the enemy has no AI.
    patrol_direction : int
        1 for right, -1 for left.
    patrol_timer : float
        Time elapsed in current patrol direction.
    patrol_interval : float
        Time before changing patrol direction.
    pushable : bool
        Whether the enemy can be pushed by attacks.
    super_armor : bool
        Whether the enemy has super armor (ignores stagger).
    """

    config: EnemyConfig
    player: PlayerReference | None
    chase_speed: float
    vision_range: float
    attack_range: float
    attack_name: str | None
    idle_duration: float
    passive_friction: float
    patrol_direction: int
    patrol_timer: float
    patrol_interval: float
    pushable: bool
    super_armor: bool

    def __init__(
        self,
        pos: Sequence[float] | Vector2,
        groups: Group | Sequence[Group],
        collision_sprites: Group,
        player_reference: PlayerReference | None,
        config: EnemyConfig,
        rng: random.Random | None = None,
    ) -> None:
        """Initialize an enemy from its configuration.

        Parameters
        ----------
        pos : Sequence[float] | Vector2
            Starting top-left position.
        groups : Group | Sequence[Group]
            Sprite group(s) to add this enemy to.
        collision_sprites : Group
            Group of sprites that block movement.
        player_reference : PlayerReference | None
            Reference to the player entity.
        config : EnemyConfig
            Data class holding enemy parameters.
        rng : random.Random | None
            Optional random number generator instance for deterministic behaviors.
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
            hurtbox_inflate=config.hurtbox_inflate,
            health=config.health,
            max_health=max_health,
            faction="enemy",
            spawn_pos=pos,
            attacks=config.attacks if config.attacks else None,
            hurt_duration=CombatSettings.HURT_DURATION,
            rng=rng,
        )

        self.config = config
        self.player = player_reference
        self.chase_speed = config.chase_speed
        self.vision_range = config.vision_range
        self.attack_range = config.attack_range
        self.attack_name = config.attack_name
        self.idle_duration = config.idle_duration
        self.passive_friction = config.passive_friction

        self.speed = self.chase_speed
        self.floor_control = 20.0
        self.air_control = 10.0

        self.patrol_direction = 1 if self.rng.random() > 0.5 else -1
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
        self.state_machine.add_state("charge", EnemyChargeState(self))
        self.state_machine.add_state("hurt", EnemyHurtState(self))
        self.state_machine.add_state("knockback", EnemyKnockbackState(self))
        self.state_machine.add_state("stagger", EnemyStaggerState(self))
        self.state_machine.set_initial_state("idle")
        self._setup_interrupts()

    def _setup_interrupts(self) -> None:
        """Register enemy-specific state machine interrupts."""
        super()._setup_interrupts()

    def face_player(self) -> None:
        """Orient the enemy toward the player if player exists."""
        if self.player is None or self.is_dead:
            return
        self.face_towards(self.player.hitbox.centerx)

    def _pre_update(self, delta_time: float) -> None:
        """Update facing direction before combat updates."""
        if self.config.has_ai and self.player is not None:
            current = self.state_machine.current_state_name
            if current not in ("attack", "hurt", "knockback", "stagger"):
                self.face_player()

    def _update_state_machine(self, delta_time: float) -> None:
        """Update AI state machine or apply passive friction if AI is disabled."""
        if self.config.has_ai:
            self.state_machine.update(delta_time)
        elif self.on_surface["floor"]:
            lerp_velocity(self, 0.0, min(
                1.0, self.passive_friction * delta_time), delta_time)

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
