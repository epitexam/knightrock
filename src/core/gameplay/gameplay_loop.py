from src.combat.combat_system import CombatSystem
from src.physics import SeparationSystem


class GameplayLoop:
    def __init__(self):
        self.combat_system = CombatSystem()
        self.separation_system = SeparationSystem()

    def begin_tick(self, delta_time: float) -> float:
        """Advance hit-stop timing and return the simulation delta for this tick."""
        simulation_suspended = self.combat_system.in_hit_stop
        self.combat_system.update_timer(delta_time)
        return 0.0 if simulation_suspended else delta_time

    def process_combat_and_separation(self, effective_delta, combat_sprites, entity_sprites):
        if effective_delta > 0.0:
            self.separation_system.process(entity_sprites)
            self.combat_system.process_attacks(combat_sprites)

    def remove_dead_entities(self, entity_sprites, player):
        dead = [e for e in entity_sprites if e.is_dead and e is not player]
        for e in dead:
            e.kill()