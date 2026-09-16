"""Orchestration of the fixed-tick systems of a level (audit F1.6 / §4).

``GameplayLoop`` owns the *order* in which a level's systems run; the systems
themselves are assembled by :class:`~src.core.level.level.Level` and injected
here, so each one stays independently testable (audit F1.2).  The level is
then a strict facade: :meth:`~src.core.level.level.Level.update` delegates
its whole tick — debug spawner, simulation, camera, notifications and
rollback bookkeeping — to :meth:`update` below.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, TypeVar

import pygame

from src.combat.combatant_protocol import Combatant
from src.core.level.systems.camera_system import CameraSystem
from src.core.level.systems.combat_system import CombatSystem
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.level.systems.hazard_system import HazardSystem
from src.core.level.systems.notification_system import NotificationSystem
from src.core.level.systems.physics_system import PhysicsSystem
from src.core.level.systems.platform_system import PlatformSystem
from src.core.level.systems.progression_system import ProgressionSystem
from src.core.level.systems.respawn_system import PlayerRespawnSystem
from src.core.level.systems.separation_system import SeparationSystem
from src.core.level.systems.spawn_system import SpawnSystem
from src.core.level.systems.tick_system import TickOwner, TickSystem

if TYPE_CHECKING:
    from src.core.level.systems.projectile_system import ProjectileSystem
from src.core.rollback import RollbackSystem
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
        spawn_system: SpawnSystem | None = None,
        camera_system: CameraSystem | None = None,
        notification_system: NotificationSystem | None = None,
        tick_system: TickSystem | None = None,
        projectile_system: ProjectileSystem | None = None,
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
        # Cross-cutting stages: head (debug spawner) and tail (camera,
        # notifications, tick bookkeeping) of the same pipeline.
        self.spawn_system = spawn_system
        self.camera_system = camera_system
        self.notification_system = notification_system
        self.tick_system = tick_system
        self.projectile_system = projectile_system

    def begin_tick(self, delta_time: float) -> float:
        """Advance hit-stop timing and return the simulation delta."""
        simulation_suspended = self.combat_system.in_hit_stop
        self.combat_system.update_timer(delta_time)
        return 0.0 if simulation_suspended else delta_time

    def update(
        self,
        raw_delta: float,
        groups: SpriteGroups,
        player: Player,
        level: TickOwner,
        rollback: RollbackSystem,
    ) -> None:
        """Run every stage of one tick, in their historical order.

        The debug spawner runs first with the raw frame delta (it only
        decays cooldowns and spawns), then hit-stop decides the simulation
        delta: a suspended tick skips the world stages but still advances
        the camera, notifications and tick bookkeeping — the level did the
        same before it became a facade.  The order is load-bearing and
        matches the pre-refactor ``Level.update`` exactly: spawner,
        platforms, hazards, entity integration, pairings, deaths reaped,
        respawn, progression, camera, notifications, tick counter.
        """
        spawn = self._require(self.spawn_system, "spawn_system")
        camera = self._require(self.camera_system, "camera_system")
        notifications = self._require(self.notification_system, "notification_system")
        tick = self._require(self.tick_system, "tick_system")
        respawn = self.respawn_system
        progression = self.progression_system

        spawn.process(raw_delta, player)
        effective_delta = self.begin_tick(raw_delta)

        if effective_delta > 0.0:
            # Resolve the stages up front: a half-wired loop must fail before
            # it mutates the world, never halfway through the tick.
            platform = self._require(self.platform_system, "platform_system")
            hazard = self._require(self.hazard_system, "hazard_system")
            physics = self._require(self.physics_system, "physics_system")
            contact = self._require(self.contact_damage_system, "contact_damage_system")
            hazard_damage = self._require(self.hazard_damage_system, "hazard_damage_system")
            respawn = self._require(respawn, "respawn_system")
            progression = self._require(progression, "progression_system")

            platform.process(effective_delta)
            hazard.process(effective_delta)
            physics.process(effective_delta)

            self.process_combat_and_separation(
                effective_delta, groups.combat_sprites, groups.entity_sprites
            )
            if self.projectile_system is not None:
                self.projectile_system.process(effective_delta, self.entity_grid)
            contact.process(groups.entity_sprites, self.entity_grid)
            hazard_damage.process(groups.entity_sprites, groups.hazard_sprites)
            self.remove_dead_entities(groups.entity_sprites, player)

            respawn.process(effective_delta)
            progression.process(player)

            camera.process(raw_delta, player)
            notifications.process(
                player,
                deaths=respawn.deaths,
                exit_reached=progression.exit_reached,
            )
            tick.process(level, rollback)
            return

        camera.process(raw_delta, player)
        notifications.process(
            player,
            deaths=respawn.deaths if respawn is not None else 0,
            exit_reached=progression.exit_reached if progression is not None else False,
        )
        tick.process(level, rollback)

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
