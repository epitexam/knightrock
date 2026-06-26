from src.combat.combat_system import CombatSystem
from src.core.separation_system import SeparationSystem


class GameplayLoop:
    def __init__(self):
        self.combat_system = CombatSystem()
        self.separation_system = SeparationSystem()

    def process_combat_and_separation(self, delta_time, combat_sprites, entity_sprites):
        self.combat_system.update_timer(delta_time)
        if not self.combat_system.in_hit_stop:
            self.separation_system.process(entity_sprites)
            self.combat_system.process_attacks(combat_sprites)

    def remove_dead_entities(self, entity_sprites, player):
        dead = [e for e in entity_sprites if e.is_dead and e is not player]
        for e in dead:
            e.kill()