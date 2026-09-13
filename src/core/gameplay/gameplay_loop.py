"""Orchestration of fixed-tick gameplay systems."""

from collections.abc import Iterable

import pygame

from src.combat.combat_system import CombatSystem
from src.combat.combatant_protocol import Combatant
from src.physics import SeparationSystem
from src.physics.entity_grid import EntityGrid


class GameplayLoop:
    def __init__(self) -> None:
        self.combat_system: CombatSystem = CombatSystem()
        self.separation_system: SeparationSystem = SeparationSystem()
        # PERF-02: per-tick hash over the live entities. Rebuilt in one O(n)
        # pass at the start of process_combat_and_separation (positions are
        # up to date there) and shared with every pairing system, turning
        # the legacy O(n²) pair loops into O(n · k) local queries.
        self.entity_grid: EntityGrid = EntityGrid(cell_size=128)

    def begin_tick(self, delta_time: float) -> float:
        """Advance hit-stop timing and return the simulation delta."""
        simulation_suspended = self.combat_system.in_hit_stop
        self.combat_system.update_timer(delta_time)
        return 0.0 if simulation_suspended else delta_time

    def process_combat_and_separation(
        self,
        effective_delta: float,
        combat_sprites: Iterable[Combatant],
        entity_sprites: pygame.sprite.Group[pygame.sprite.Sprite],
    ) -> None:
        if effective_delta <= 0.0:
            return

        self.entity_grid.rebuild(entity_sprites)
        self.separation_system.process(entity_sprites, self.entity_grid)
        combatants = tuple(combat_sprites)
        for combatant in combatants:
            combatant.combat.sync_attack_box()
        self.combat_system.process_attacks(combatants, self.entity_grid)

    def remove_dead_entities(
        self,
        entity_sprites: Iterable[pygame.sprite.Sprite],
        player: pygame.sprite.Sprite | None,
    ) -> None:
        for entity in tuple(entity_sprites):
            if getattr(entity, "is_dead", False) and entity is not player:
                entity.kill()
