"""
State machine states for enemies (AI).
"""

from typing import Optional, Any
from src.states.state_machine import State


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


class EnemyHurtState(State):
    """Hurt state: reaction to taking damage."""

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state. Can accept knockback_direction from kwargs."""
        pass

    def update(self, delta_time: float) -> Optional[str]:
        """Update the state and return to idle when hurt duration ends."""
        if not self.entity.combat.is_hurt:
            self.entity.state_machine.change_state("idle")
        return None


class EnemyStaggerState(State):
    """Stagger state: stunned and unable to act."""

    def enter(self, previous: Optional[str] = None, **kwargs: Any) -> None:
        """Enter the state."""
        pass

    def update(self, delta_time: float) -> Optional[str]:
        """Update the state and return to idle when stagger timer ends."""
        if self.entity.stagger_timer <= 0:
            self.entity.state_machine.change_state("idle")
        return None
