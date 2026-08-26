"""Orchestration of fixed-tick gameplay systems."""

from collections.abc import Iterable

import pygame

from src.combat.combat_system import CombatSystem
from src.combat.combatant_protocol import Combatant
from src.physics import SeparationSystem


class GameplayLoop:
    def __init__(self) -> None:
        self.combat_system: CombatSystem = CombatSystem()
        self.separation_system: SeparationSystem = SeparationSystem()

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

        self.separation_system.process(entity_sprites)
        combatants = tuple(combat_sprites)
        for combatant in combatants:
            combatant.combat.sync_attack_box()
        self.combat_system.process_attacks(combatants)

    def remove_dead_entities(
        self,
        entity_sprites: Iterable[pygame.sprite.Sprite],
        player: pygame.sprite.Sprite | None,
    ) -> None:
        for entity in tuple(entity_sprites):
            if getattr(entity, "is_dead", False) and entity is not player:
                entity.kill()
