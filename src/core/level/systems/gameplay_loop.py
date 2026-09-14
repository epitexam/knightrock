"""Orchestration of the fixed-tick systems of a level (audit F1.6 / §4).

``GameplayLoop`` owns the *order* in which a level's systems run; the systems
themselves are assembled by :class:`~src.core.level.level.Level` and injected
here, so each one stays independently testable (audit F1.2).  The level is
then a facade: it drives the debug spawner, delegates the simulation to this
pipeline, and runs its cross-cutting tail (camera, events, rollback).
"""

from collections.abc import Iterable
from typing import TypeVar

import pygame

from src.combat.combatant_protocol import Combatant
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.level.systems.hazard_system import HazardSystem
from src.core.level.systems.physics_system import PhysicsSystem
from src.core.level.systems.platform_system import PlatformSystem
from src.core.level.systems.progression_system import ProgressionSystem
from src.core.level.systems.respawn_system import PlayerRespawnSystem
from src.core.level.systems.separation_system import SeparationSystem
from src.core.sprite_groups import SpriteGroups
from src.entities.player import Player
from src.physics.entity_grid import EntityGrid

__all__ = ["GameplayLoop"]

_Stage = TypeVar("_Stage")


class GameplayLoop:
    """Sequence a level's systems for one fixed simulation tick.

    The combat core (hit-stop, separation, hit detection) is always present,
    so ``GameplayLoop()`` stays usable on its own in unit tests.  The world
    stages are injected by the level and are required by :meth:`update`,
    which fails fast with a wiring hint when one is missing.
    """

    def __init__(
        self,
        platform_system: PlatformSystem | None = None,
        physics_system: PhysicsSystem | None = None,
        hazard_system: HazardSystem | None = None,
        contact_damage_system: ContactDamageSystem | None = None,
        hazard_damage_system: HazardDamageSystem | None = None,
        respawn_system: PlayerRespawnSystem | None = None,
        progression_system: ProgressionSystem | None = None,
    ) -> None:
        self.combat_system: CombatSystem = CombatSystem()
        self.separation_system: SeparationSystem = SeparationSystem()
        # PERF-02: per-tick hash over the live entities. Rebuilt in one O(n)
        # pass at the start of process_combat_and_separation (positions are
        # up to date there) and shared with every pairing system, turning
        # the legacy O(n²) pair loops into O(n · k) local queries.
        self.entity_grid: EntityGrid = EntityGrid(cell_size=128)

        # World stages, assembled by the level and run in the order below.
        self.platform_system = platform_system
        self.physics_system = physics_system
        self.hazard_system = hazard_system
        self.contact_damage_system = contact_damage_system
        self.hazard_damage_system = hazard_damage_system
        self.respawn_system = respawn_system
        self.progression_system = progression_system

    def begin_tick(self, delta_time: float) -> float:
        """Advance hit-stop timing and return the simulation delta."""
        simulation_suspended = self.combat_system.in_hit_stop
        self.combat_system.update_timer(delta_time)
        return 0.0 if simulation_suspended else delta_time

    def update(
        self,
        effective_delta: float,
        groups: SpriteGroups,
        player: Player,
    ) -> None:
        """Run every stage of one simulation tick, in their historical order.

        A suspended tick (``effective_delta == 0``, i.e. hit-stop) runs no
        stage at all — the level still advances its camera, notifications and
        rollback outside this pipeline.  The order is load-bearing and matches
        the pre-refactor ``Level.update`` exactly: platforms move, hazards
        tick, entities integrate, pairings resolve, deaths are reaped, then
        respawn and progression are evaluated.
        """
        if effective_delta <= 0.0:
            return

        # Resolve the stages up front: a half-wired loop must fail before it
        # mutates the world, never halfway through the tick.
        platform = self._require(self.platform_system, "platform_system")
        hazard = self._require(self.hazard_system, "hazard_system")
        physics = self._require(self.physics_system, "physics_system")
        contact = self._require(self.contact_damage_system, "contact_damage_system")
        hazard_damage = self._require(self.hazard_damage_system, "hazard_damage_system")
        respawn = self._require(self.respawn_system, "respawn_system")
        progression = self._require(self.progression_system, "progression_system")

        platform.process(effective_delta)
        hazard.process(effective_delta)
        physics.process(effective_delta)

        self.process_combat_and_separation(
            effective_delta, groups.combat_sprites, groups.entity_sprites
        )
        contact.process(groups.entity_sprites, self.entity_grid)
        hazard_damage.process(groups.entity_sprites, groups.hazard_sprites)
        self.remove_dead_entities(groups.entity_sprites, player)

        respawn.process(effective_delta)
        progression.process(player)

    @staticmethod
    def _require(system: _Stage | None, name: str) -> _Stage:
        """Return an injected stage, or fail fast with a wiring hint."""
        if system is None:
            raise RuntimeError(
                f"GameplayLoop.update() needs the {name!r} stage: assemble it "
                "in Level and pass it to GameplayLoop(...)."
            )
        return system

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
