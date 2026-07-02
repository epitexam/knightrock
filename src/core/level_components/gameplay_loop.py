from src.combat.combat_system import CombatSystem
from src.physics import SeparationSystem


class GameplayLoop:
    """Process combat and entity updates each frame."""
    def __init__(self):
        """Initialize the GameplayLoop instance."""
        self.combat_system = CombatSystem()
        self.separation_system = SeparationSystem()

    def process_combat_and_separation(self, delta_time, combat_sprites, entity_sprites):
        """Process combat and separation."""
        self.combat_system.update_timer(delta_time)
        if not self.combat_system.in_hit_stop:
            self.separation_system.process(entity_sprites)
            self.combat_system.process_attacks(combat_sprites)

    def remove_dead_entities(self, entity_sprites, player):
        """Remove dead entities."""
        dead = [e for e in entity_sprites if e.is_dead and e is not player]
        for e in dead:
            e.kill()
