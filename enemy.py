from entity import Entity
from state_machine import State, StateMachine


class EnemyPatrolState(State):
    def update(self, delta_time: float) -> str | None:
        if self.entity.can_see_player():
            return "chase"
        return None


class EnemyChaseState(State):
    def update(self, delta_time: float) -> str | None:
        if self.entity.is_player_in_range():
            return "attack"
        if not self.entity.can_see_player():
            return "patrol"
        return None


class Goblin(Entity):
    def __init__(self, pos, groups, collision_sprites, player_reference):
        super().__init__(pos, (48, 48), (200, 50, 50), groups, collision_sprites)
        self.player = player_reference

        self.state_machine = StateMachine(self)
        self.state_machine.add_state("patrol", EnemyPatrolState(self))
        self.state_machine.add_state("chase", EnemyChaseState(self))
        self.state_machine.set_initial_state("patrol")

    def update(self, delta_time: float) -> None:
        assert self.state_machine is not None
        self.state_machine.update(delta_time)

        self.apply_gravity(delta_time)
        self.hitbox.x += self.velocity.x * delta_time
        self.handle_collisions("horizontal")
