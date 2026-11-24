"""Orchestration of the fixed-tick systems of a level.

``GameplayLoop`` owns the *order* in which a level's systems run; the systems
themselves are assembled by :class:`~src.core.level.level.Level` and injected
here, so each one stays independently testable.  The level is
then a strict facade: :meth:`~src.core.level.level.Level.update` delegates
its whole tick — debug spawner, simulation, camera, notifications and
rollback bookkeeping — to :meth:`update` below.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

import pygame

from src.combat.combatant_protocol import Combatant
from src.core.level.systems.camera_system import CameraSystem
from src.core.level.systems.combat_system import CombatSystem, GuardEvent
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.contact_system import ContactSystem, ImpactEvent
from src.core.level.systems.feedback_system import FeedbackSystem
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
from src.core.settings import World
from src.core.sprite_groups import SpriteGroups
from src.entities.player import Player
from src.physics.entity_grid import EntityGrid

__all__ = ["CombatLoop", "GameplayLoop"]


class CombatLoop:
    """The combat core of a tick: hit-stop, separation, hit detection, reaping.

    Usable on its own, which is what the combat tests build. A level builds a
    :class:`GameplayLoop`, which is this core plus every world stage.
    """

    def __init__(
        self,
        contact_system: ContactSystem | None = None,
        feedback_system: FeedbackSystem | None = None,
    ) -> None:
        # Unified offensive-contact pipeline: one shared engine for
        # melee, projectiles, hazards and contact damage (injected by Level
        # in production; created here for combat-only test fixtures). Its
        # tick accumulator is what the debug metrics panel surfaces.
        self.contact_system: ContactSystem = (
            contact_system if contact_system is not None else ContactSystem()
        )
        self.combat_system: CombatSystem = CombatSystem(contact_system=self.contact_system)
        self.separation_system: SeparationSystem = SeparationSystem()
        # Per-tick hash over the live entities, rebuilt in one O(n) pass at the
        # start of ``process_combat_and_separation`` and shared with every
        # pairing system, so a pair search is a local query.
        self.entity_grid: EntityGrid = EntityGrid(cell_size=World.HASH_CELL_SIZE)
        #: Leaves a body behind for a reaped fighter; nothing without one.
        self.reaper_feedback: FeedbackSystem | None = feedback_system

    def begin_tick(self, delta_time: float) -> float:
        """Advance hit-stop timing and return the simulation delta."""
        simulation_suspended = self.combat_system.in_hit_stop
        self.combat_system.update_timer(delta_time)
        if not simulation_suspended:
            self.contact_system.begin_tick()
        return 0.0 if simulation_suspended else delta_time

    def _collect_guard_events(self) -> list[GuardEvent]:
        """Take this tick's guard events from the melee system."""
        events = list(self.combat_system.guard_events)
        self.combat_system.guard_events.clear()
        return events

    def _collect_impact_events(self) -> list[ImpactEvent]:
        """Take this tick's landed hits from the melee system."""
        events = list(self.combat_system.impact_events)
        self.combat_system.impact_events.clear()
        return events

    @staticmethod
    def _fighters(groups: SpriteGroups) -> tuple[Entity, ...]:
        """Dense rows first, then any sprite filed without going through add_fighter.

        A few test fixtures -- and a legacy debug path -- add a fighter straight
        to ``entity_sprites``. Those have no dense row, so the roster is their
        union: no fighter silently disappears from the tick because it skipped
        the registration seam.
        """
        table = groups.movement_table
        if table is None:
            return tuple(groups.entity_sprites)  # type: ignore[arg-type]
        bound = tuple(table.iter_entities())
        bound_ids = {id(entity) for entity in bound}
        extra = tuple(
            cast(Entity, getattr(sprite, "entity", sprite))
            for sprite in groups.entity_sprites
            if id(getattr(sprite, "entity", sprite)) not in bound_ids
        )
        return bound + extra

    def process_combat_and_separation(
        self,
        effective_delta: float,
        combat_sprites: Iterable[Combatant],
        entity_sprites: pygame.sprite.Group[Any],
        groups: SpriteGroups | None = None,
    ) -> None:
        if effective_delta <= 0.0:
            return

        fighters = self._fighters(groups) if groups is not None else tuple(entity_sprites)
        self.entity_grid.rebuild(fighters)
        displaced = self.separation_system.process(fighters, self.entity_grid)
        combat_table = groups.combat_table if groups is not None else None
        combatants = fighters if combat_table is not None else tuple(combat_sprites)
        # Only the fighters separation actually pushed need their attack box
        # re-positioned: it is derived from the hitbox, and separation moved
        # that after ``Entity.update`` had already synced it.
        for combatant in displaced:
            combatant.combat.sync_attack_box()
        self.combat_system.process_attacks(combatants, self.entity_grid)

    def remove_dead_entities(
        self,
        entity_sprites: Iterable[Entity],
        player: Entity | None,
    ) -> None:
        for sprite in tuple(entity_sprites):
            entity = getattr(sprite, "entity", sprite)
            if entity.is_dead and entity is not player:
                if self.reaper_feedback is not None:
                    self.reaper_feedback.before_removal(entity)
                entity.kill()


class GameplayLoop(CombatLoop):
    """Sequence a level's systems for one fixed simulation tick.

    Every stage is required: a loop that cannot run a tick cannot be built,
    so there is nothing for :meth:`update` to check before it starts. The
    combat core alone is :class:`CombatLoop`.
    """

    def __init__(
        self,
        *,
        platform_system: PlatformSystem,
        physics_system: PhysicsSystem,
        hazard_system: HazardSystem,
        contact_damage_system: ContactDamageSystem,
        hazard_damage_system: HazardDamageSystem,
        respawn_system: PlayerRespawnSystem,
        progression_system: ProgressionSystem,
        spawn_system: SpawnSystem,
        camera_system: CameraSystem,
        notification_system: NotificationSystem,
        tick_system: TickSystem,
        projectile_system: ProjectileSystem,
        feedback_system: FeedbackSystem,
        contact_system: ContactSystem | None = None,
    ) -> None:
        super().__init__(contact_system=contact_system, feedback_system=feedback_system)
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
        self.feedback_system = feedback_system

    def update(
        self,
        raw_delta: float,
        groups: SpriteGroups,
        player: Player,
        level: TickOwner,
        rollback: RollbackSystem,
    ) -> None:
        """Run every stage of one tick, in the order below.

        Stage          | Purpose                         | Order invariant
        ---------------|---------------------------------|----------------------
        spawner        | decay cooldowns, debug spawns   | raw delta, before hit-stop
        hit-stop       | decide the simulation delta     | a frozen tick skips the world
        sweep origins  | capture this tick's geometry    | before any movement or attack
        platforms      | move carried platforms          | before entity integration
        hazards        | move hazards                    | before entity integration
        physics        | integrate entities              | before separation / melee
        feedback       | movement feedback               | after physics
        launch shots   | drain phase launches            | before combat resolution
        combat+separation | melee pairs, push apart      | after physics, before projectiles
        projectiles    | advance and resolve shots       | after launch, after melee
        damage         | contact and hazard damage       | after all offensive boxes exist
        deaths         | reap the dead                   | after damage
        respawn        | place the respawned             | after reaping
        progression    | exit flag                       | after respawn
        camera         | ease toward the player          | frozen ticks still run it
        notifications  | emit level milestones           | frozen ticks still run it
        tick counter   | record the rollback snapshot    | last, after everything above

        The entity grid is rebuilt at the start of ``process_combat_and_separation``,
        *before* separation pushes entities apart; the damage systems that follow
        reuse that same grid. Reordering either step silently changes collision
        results, which is why the order is listed here in one place.
        """
        for fighter in groups.entity_sprites:
            fighter.render_hints.previous_center = fighter.hitbox.center  # type: ignore[attr-defined]
        self.spawn_system.process(raw_delta, player)
        effective_delta = self.begin_tick(raw_delta)
        fighters = self._fighters(groups)

        if effective_delta > 0.0:
            # The tick frontier: one capture per tick, before any movement or
            # attack start, so a sweep covers the whole tick including the
            # platform carry. Covers sprites spawned this tick too.
            for sprite in fighters:
                if isinstance(sprite, Entity):
                    sprite.capture_sweep_origin()
            for combatant in groups.combat_sprites:
                combatant.combat.capture_attack_origin()
            # A perfect dodge slows the world and not the player: everything
            # but the player runs on ``world_delta`` until the rush is over.
            world_delta = effective_delta * player.world_time_scale
            self.platform_system.process(world_delta)
            self.hazard_system.process(world_delta)
            self.physics_system.process(effective_delta, world_delta, player)
            self.feedback_system.after_movement(effective_delta)
            self._launch_shots(groups.combat_sprites)

            self.process_combat_and_separation(
                effective_delta, groups.combat_sprites, groups.entity_sprites, groups
            )
            self.projectile_system.process(world_delta, self.entity_grid)
            self.feedback_system.after_combat(
                self.combat_system.impact,
                self._collect_guard_events(),
                player,
                self.camera_system,
                self._collect_impact_events(),
            )
            self.contact_damage_system.process(fighters, self.entity_grid)
            self.hazard_damage_system.process(fighters, groups.hazard_sprites, self.entity_grid)
            self._flush_combat_trace()
            self.remove_dead_entities(fighters, player)

            self.respawn_system.process(effective_delta, fighters)
            self.progression_system.process(player)

        # The tail runs on a frozen tick too: the camera keeps easing and the
        # tick is still counted and recorded.
        self.camera_system.process(raw_delta, player)
        self.notification_system.process(
            player,
            deaths=self.respawn_system.deaths,
            exit_reached=self.progression_system.exit_reached,
        )
        self.tick_system.process(level, rollback)

    def _launch_shots(self, combatants: Iterable[Combatant]) -> None:
        """Put in flight every shot a phase threw this tick, from the hand forward."""
        from src.entities.shots import SHOTS, charged

        for fighter in combatants:
            for name, charge in fighter.combat.state.take_launches():
                spec = charged(SHOTS[name], charge)
                side = 1.0 if fighter.facing_right else -1.0
                width, height = spec.config.size
                x = fighter.hitbox.centerx + spec.muzzle[0] * side - width / 2.0
                y = fighter.hitbox.centery + spec.muzzle[1] - height / 2.0
                self.projectile_system.spawn(
                    spec.config,
                    pos=(x, y),
                    velocity=(spec.speed * side, spec.rise),
                    faction=fighter.faction,
                )

    def _flush_combat_trace(self) -> None:
        """Dump the buffered hit candidates when the debug trace is on.

        Off-by-default (``DEBUG`` + ``DEBUG_COMBAT_DUMP``); the path lives
        under ``logs/`` next to the rotating handler configured in main.
        """
        trace = self.contact_system.trace
        if not trace.enabled or len(trace) == 0:
            return
        from pathlib import Path  # local: keep import cost off the hot path

        trace.drain_jsonl(Path("logs") / "combat_trace.jsonl")

    def _collect_guard_events(self) -> list[GuardEvent]:
        """Take this tick's guard events from the melee and projectile systems."""
        events = super()._collect_guard_events()
        events.extend(self.projectile_system.guard_events)
        self.projectile_system.guard_events.clear()
        return events

    def _collect_impact_events(self) -> list[ImpactEvent]:
        """Take this tick's landed hits from the melee and projectile systems."""
        events = super()._collect_impact_events()
        events.extend(self.projectile_system.impact_events)
        self.projectile_system.impact_events.clear()
        return events
