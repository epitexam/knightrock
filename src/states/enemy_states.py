"""State machine states for enemies (AI)."""

from typing import Optional, Any
from src.states.state_machine import State
from src.states.reaction_states import (
    HurtState,
    KnockbackState,
    StaggerState,
)


class EnemyIdleState(State):
    """Idle state: the enemy stands still for a short duration."""

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state and initialize the idle timer."""
        self.timer = self.entity.idle_duration

    def update(self, delta_time: float) -> Optional[str]:
        """Update the state and transition to patrol or chase."""
        self.timer -= delta_time
        if self.timer <= 0:
            if self.entity.can_see_player():
                self.entity.state_machine.change_state("chase")
            else:
                self.entity.state_machine.change_state("patrol")
        return None


class EnemyPatrolState(State):
    """Patrol state: the enemy moves back and forth in a single direction."""

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state and initialize patrol direction and timer."""
        self.patrol_timer = self.entity.patrol_interval
        self.direction = self.entity.patrol_direction

    def update(self, delta_time: float) -> Optional[str]:
        """Update the state, move the enemy, and check for player detection."""
        self.entity.move_axis = self.direction
        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.can_see_player():
            self.entity.state_machine.change_state("chase")
            return None

        self.patrol_timer -= delta_time
        if self.patrol_timer <= 0:
            self.direction *= -1
            self.patrol_timer = self.entity.patrol_interval
            self.entity.facing_right = self.direction > 0
        return None

    def exit(self, next_state: Optional[str] = None) -> None:
        """Exit the state and reset movement axis."""
        self.entity.move_axis = 0.0


class EnemyChaseState(State):
    """Chase state: the enemy moves towards the player."""

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state and face the player."""
        self.entity.face_player()

    def update(self, delta_time: float) -> Optional[str]:
        """Update the state, move towards the player, and check attack range."""
        if self.entity.player is None:
            self.entity.state_machine.change_state("idle")
            return None

        player_center = self.entity.player.hitbox.centerx
        enemy_center = self.entity.hitbox.centerx
        if abs(player_center - enemy_center) < 10:
            self.entity.move_axis = 0.0
        else:
            self.entity.move_axis = 1.0 if player_center > enemy_center else -1.0
            self.entity.facing_right = self.entity.move_axis > 0

        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.is_player_in_range():
            self.entity.state_machine.change_state("attack")
        elif not self.entity.can_see_player():
            self.entity.state_machine.change_state("idle")
        return None


class EnemyAttackState(State):
    """Attack state: the enemy performs its attack."""

    def __init__(self, entity: Any, tags: Optional[list[str]] = None):
        """Initialize the EnemyAttackState instance."""
        super().__init__(entity, tags or ["attack", "busy"])

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state, face the player, and start the attack."""
        self.entity.face_player()

        if self.entity.attack_name is not None:
            self.entity.combat.start_attack(self.entity.attack_name)
        self._started = True

    def update(self, delta_time: float) -> Optional[str]:
        """Update the state and return to idle when the attack finishes."""
        if not self.entity.combat.is_attacking:
            self.entity.state_machine.change_state("idle")
        return None

    def exit(self, next_state: Optional[str] = None) -> None:
        """Exit the state."""
        self._started = False


class EnemyChargeState(State):
    """Charge state: the enemy is charging an attack."""

    def __init__(self, entity: Any, tags: Optional[list[str]] = None):
        """Initialize the EnemyChargeState instance."""
        super().__init__(entity, tags or ["charge", "busy"])

    def update(self, delta_time: float) -> Optional[str]:
        """Update the state and transition to attack when charge is released."""
        if not self.entity.combat.charging.is_charging:
            if self.entity.combat.is_attacking:
                self.entity.state_machine.change_state("attack")
            else:
                self.entity.state_machine.change_state("idle")
        return None


class EnemyHurtState(HurtState):
    """Hurt reaction: return to idle when the hurt timer clears.

    Shares the generic :class:`HurtState` logic (ARCH-05); enemies hold no
    knockback impulse and no friction on hurt.
    """

    def __init__(self, entity: Any):
        super().__init__(entity, exit_resolver=lambda: "idle", tags=[])


class EnemyKnockbackState(KnockbackState):
    """Knockback reaction: return to hurt/idle when the enemy stops sliding."""

    def __init__(self, entity: Any):
        super().__init__(
            entity,
            exit_resolver=self._resolve_exit,
            tags=["knockback", "busy"],
        )

    def _resolve_exit(self) -> str:
        """Recover through hurt if still hurt, otherwise to idle."""
        return "hurt" if self.entity.combat.is_hurt else "idle"


class EnemyStaggerState(StaggerState):
    """Stagger reaction: return to idle when the stagger timer clears."""

    def __init__(self, entity: Any):
        super().__init__(entity, exit_resolver=lambda: "idle", tags=[])
