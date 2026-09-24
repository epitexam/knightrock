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
from src.core.level.systems.combat_system import CombatSystem, GuardEvent
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.contact_system import ContactSystem
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
from src.entities.entity import Entity

if TYPE_CHECKING:
    from src.core.level.systems.projectile_system import ProjectileSystem
from src.core.rollback import RollbackSystem
from src.core.settings import CameraShake
from src.core.settings import Combat as CombatSettings
from src.core.settings import Guard as GuardSettings
from src.core.sprite_groups import SpriteGroups
from src.entities.player import Player
from src.physics.entity_grid import EntityGrid

__all__ = ["GameplayLoop"]

_Stage = TypeVar("_Stage")


class GameplayLoop:
    """Sequence a level's systems for one fixed simulation tick.

    The combat core (hit-stop, separation, hit detection) is always present,
    so :meth:`combat_only` stays usable on its own in unit tests.  The world
    stages are injected by the level and are required by :meth:`update`,
    which validates the full wiring up front — before any mutation — and
    fails fast with a wiring hint when one is missing.
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
        contact_system: ContactSystem | None = None,
    ) -> None:
        # Unified offensive-contact pipeline (P4.1): one shared engine for
        # melee, projectiles, hazards and contact damage (injected by Level
        # in production; created here for combat-only test fixtures). Its
        # tick accumulator is what the debug metrics panel surfaces.
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )
        self.combat_system: CombatSystem = CombatSystem(
            contact_system=self.contact_system
        )
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

    @classmethod
    def combat_only(cls) -> GameplayLoop:
        """Combat/separation core without world stages.

        Explicit assembly fixture: ``begin_tick``,
        ``process_combat_and_separation`` and ``remove_dead_entities`` stay
        usable; ``update()`` raises ``RuntimeError`` before any mutation.
        """
        return cls()

    def begin_tick(self, delta_time: float) -> float:
        """Advance hit-stop timing and return the simulation delta."""
        simulation_suspended = self.combat_system.in_hit_stop
        self.combat_system.update_timer(delta_time)
        if not simulation_suspended:
            self.contact_system.begin_tick()
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

        The full wiring (spawner, world stages, camera, notifications,
        tick) is resolved up front, before the spawner or hit-stop mutate
        anything: an invalid assembly raises ``RuntimeError`` without
        touching cooldowns, hit-stop, groups, tick or rollback.
        """
        spawn = self._require(self.spawn_system, "spawn_system")
        camera = self._require(self.camera_system, "camera_system")
        notifications = self._require(self.notification_system, "notification_system")
        tick = self._require(self.tick_system, "tick_system")
        platform = self._require(self.platform_system, "platform_system")
        hazard = self._require(self.hazard_system, "hazard_system")
        physics = self._require(self.physics_system, "physics_system")
        contact = self._require(self.contact_damage_system, "contact_damage_system")
        hazard_damage = self._require(self.hazard_damage_system, "hazard_damage_system")
        respawn = self._require(self.respawn_system, "respawn_system")
        progression = self._require(self.progression_system, "progression_system")

        spawn.process(raw_delta, player)
        effective_delta = self.begin_tick(raw_delta)

        if effective_delta > 0.0:
            # P1 sweep (D1/D3): tick-frontier capture. One explicit capture
            # per tick, before any movement or attack start of the tick —
            # covering the pre-carry segment, unlike a start-of-``update``
            # capture that would run after the platform carry. ``update``
            # positioning stays pure/idempotent, so the double sync stays
            # harmless. Covers spawn-adjacent sprites too (both sides of
            # the loop boundary).
            for sprite in groups.entity_sprites:
                if isinstance(sprite, Entity):
                    sprite.capture_sweep_origin()
            for combatant in groups.combat_sprites:
                combatant.combat.capture_attack_origin()
            platform.process(effective_delta)
            hazard.process(effective_delta)
            physics.process(effective_delta)

            self.process_combat_and_separation(
                effective_delta, groups.combat_sprites, groups.entity_sprites
            )
            impact = float(getattr(self.combat_system, "impact", 0.0) or 0.0)
            if impact >= CombatSettings.HEAVY_KNOCKBACK_THRESHOLD:
                camera.add_trauma(impact / CameraShake.HEAVY_DIV)
            if self.projectile_system is not None:
                self.projectile_system.process(effective_delta, self.entity_grid)
            self._emit_guard_fx(groups, camera)
            # Dash start screen shake
            if getattr(player, "_dash_started_this_frame", False):
                player._dash_started_this_frame = False
                camera.add_trauma(GuardSettings.PARRY_TRAUMA * 0.4)
            contact.process(groups.entity_sprites, self.entity_grid)
            hazard_damage.process(
                groups.entity_sprites, groups.hazard_sprites, self.entity_grid
            )
            self._flush_combat_trace()
            self.remove_dead_entities(groups.entity_sprites, player)

            respawn.process(effective_delta, groups.entity_sprites)
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
            deaths=respawn.deaths,
            exit_reached=progression.exit_reached,
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

    def _flush_combat_trace(self) -> None:
        """Axe G: dump buffered HitCandidates when the debug trace is on.

        Off-by-default (``DEBUG`` + ``DEBUG_COMBAT_DUMP``); the path lives
        under ``logs/`` next to the rotating handler configured in main.
        """
        trace = getattr(self.contact_system, "trace", None)
        if trace is None or not trace.enabled or len(trace) == 0:
            return
        from pathlib import Path  # local: keep import cost off the hot path

        trace.drain_jsonl(Path("logs") / "combat_trace.jsonl")

    def _emit_guard_fx(self, groups: SpriteGroups, camera: CameraSystem) -> None:
        events = self._collect_guard_events()
        if not events:
            return
        self._spawn_guard_fx(events, groups, camera)

    def _collect_guard_events(self) -> list[GuardEvent]:
        events = list(getattr(self.combat_system, "guard_events", None) or [])
        if hasattr(self.combat_system, "guard_events"):
            self.combat_system.guard_events.clear()
        projectile_system = self.projectile_system
        if projectile_system is not None:
            events.extend(getattr(projectile_system, "guard_events", None) or [])
            if hasattr(projectile_system, "guard_events"):
                projectile_system.guard_events.clear()
        return events

    def _spawn_guard_fx(
        self, events: list[GuardEvent], groups: SpriteGroups, camera: CameraSystem
    ) -> None:
        fx_group = getattr(groups, "fx_sprites", None)
        if fx_group is None:
            return

        trauma = 0.0
        for event in events:
            trauma = max(trauma, self._trauma_for_event(event))
            self._spawn_fx_for_event(event, fx_group)
        if trauma > 0.0 and hasattr(camera, "add_trauma"):
            camera.add_trauma(trauma)

    def _trauma_for_event(self, event: GuardEvent) -> float:
        if event.kind == "parry":
            return GuardSettings.PARRY_TRAUMA
        if event.kind in ("break", "stun"):
            return GuardSettings.BREAK_TRAUMA
        return GuardSettings.GUARD_TRAUMA

    def _spawn_fx_for_event(self, event: GuardEvent, fx_group: pygame.sprite.Group) -> None:
        from src.core.fx import (  # noqa: PLC0415
            spawn_break_burst,
            spawn_dizzy_stars,
            spawn_guard_spark,
            spawn_parry_burst,
        )

        if event.kind == "parry":
            spawn_parry_burst(fx_group, event.target)
        elif event.kind == "break":
            spawn_break_burst(fx_group, event.target)
        elif event.kind == "stun":
            spawn_dizzy_stars(fx_group, event.target)
        else:
            spawn_guard_spark(fx_group, event.target)

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
