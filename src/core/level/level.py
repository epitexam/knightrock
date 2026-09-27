"""
The Level facade: it builds a world and delegates its tick to the systems.
"""

import logging
from collections.abc import Iterable
from typing import Any

import pygame

from src.application.events import EventBus, LevelStarted
from src.core.input.input_manager import InputManager
from src.core.level.level_data import LevelData
from src.core.level.scene_host import SceneHost
from src.core.level.systems.camera_system import CameraSystem
from src.core.level.systems.contact_damage import ContactDamageSystem
from src.core.level.systems.contact_system import ContactSystem
from src.core.level.systems.gameplay_loop import GameplayLoop
from src.core.level.systems.hazard_damage import HazardDamageSystem
from src.core.level.systems.hazard_system import HazardSystem
from src.core.level.systems.notification_system import NotificationSystem
from src.core.level.systems.physics_system import PhysicsSystem
from src.core.level.systems.platform_system import PlatformSystem
from src.core.level.systems.progression_system import ProgressionSystem
from src.core.level.systems.projectile_system import ProjectileSystem
from src.core.level.systems.respawn_system import PlayerRespawnSystem
from src.core.level.systems.spawn_system import SpawnSystem
from src.core.level.systems.tick_system import TickSystem
from src.core.level.world_builder import WorldBuilder
from src.core.rendering.camera import Camera
from src.core.rendering.overlay import WorldOverlay
from src.core.rendering.renderer import Renderer
from src.core.rendering.tile_chunk_index import TileChunkIndex
from src.core.rollback import LevelSnapshot, PlatformSnapshot, RollbackSystem
from src.core.settings import Debug, World
from src.core.sprite_groups import SpriteGroups
from src.data.provider import GameplayData
from src.entities.entity import EntitySnapshot
from src.entities.player import Player
from src.physics.spatial_hash import SpatialHash

logger = logging.getLogger(__name__)


class Level:
    """
    One game level: world assembly, simulation entry point and rendering.

    The level owns the world (sprite groups, camera, spatial hash), assembles
    the systems that make up its tick, and re-exposes the state they hold
    (``respawn_timer``/``deaths``/``exit_reached``) directly from them.

    It is a *strict facade* over those systems (audit F1.2/§4): :meth:`update`
    is a single delegation to
    :meth:`~src.core.level.systems.gameplay_loop.GameplayLoop.update` — the
    debug spawner, every simulation stage, the camera follow, the event-bus
    notifications and the end-of-tick rollback snapshot all run inside the
    pipeline now.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        level_data: LevelData,
        input_manager: InputManager,
        level_id: int = 0,
        events: EventBus | None = None,
        rollback_enabled: bool = False,
        gameplay_data: GameplayData | None = None,
        overlay: WorldOverlay | None = None,
    ) -> None:
        """
        Initialize the level from parsed TMX data and build the world.

        Args:
            surface: The Pygame surface to draw on.
            level_data: Parsed level data containing tile layers and objects.
            input_manager: The input manager used by the player.
            level_id: Numeric id of the level (event payloads, Phase 2 #5).
            events: Optional event bus; emissions are notifications only
                (subscribers must never mutate the simulation).
            rollback_enabled: Opt-in per-tick snapshot recording for the
                local rollback core (Phase 3 #3). Off by default: recording
                costs a full state capture each tick and only netcode,
                rewind-the-tape, or tests need it.
            gameplay_data: Optional gameplay-data bundle (Phase 3 #4).
                When given, the player config, enemy configs and level
                paths are taken from the JSON assets instead of the
                built-in Python values.
        """
        self.surface = surface
        self.input_manager = input_manager
        self.level_data = level_data

        self.groups = SpriteGroups()

        # La caméra ne connaît plus la fenêtre : elle reçoit le cadrage, qui est
        # une constante en unités monde, et lit son échelle sur la cible de rendu
        # qu'on lui passe. C'est ce qui fait qu'une résolution ne peut plus
        # élargir ce que le joueur voit — le viewport est le même sur un portable
        # 1366x768 et sur un écran 4K.
        self.camera = Camera.for_target(surface)
        self.camera.set_world_size(level_data.pixel_width, level_data.pixel_height)

        # ``exit_reached``, ``respawn_timer`` and ``deaths`` live in the
        # systems assembled below and are re-exposed as properties (audit F1.2).
        self.level_id = level_id
        self.events = events

        # Local rollback core (Phase 3 #3): monotonic fixed-tick counter and
        # the ring buffer that captures a snapshot at the end of each tick.
        # Recording is opt-in because a capture costs a full state copy.
        self.tick = 0
        self.rollback_enabled = rollback_enabled
        self.rollback = RollbackSystem()

        self.renderer = Renderer(self.surface, self.camera, level_data.config, overlay)
        # Spatial hash for O(1) collision lookups (PERF-01/02). Created before
        # the world build, not before the spawner: what the build needs is the
        # grid, so that every entity it creates is wired into it from the start.
        self.spatial_hash = SpatialHash(cell_size=World.HASH_CELL_SIZE)

        self.world_builder = WorldBuilder(level_data, gameplay_data)
        # The grid is bound *before* the build so every entity comes out of the
        # world builder already wired. Entities created by a registry or object
        # factory behind the builder's back are still swept up by the pass
        # below, so no creation path can end up without one.
        self.world_builder.bind_spatial_hash(self.spatial_hash)
        self.player: Player = self.world_builder.build(self.groups, self.input_manager)

        self._install_static_culls()

        # Bucket the static collidables once; entities query the grid every
        # tick, so each one must know it (moving platforms are re-bucketed
        # each tick by PlatformSystem).
        self.spatial_hash.add_all(self.groups.collision_sprites)
        for entity in self.groups.entity_sprites:
            if entity.spatial_hash is None:
                entity.spatial_hash = self.spatial_hash
        for platform in self.groups.moving_platforms:
            # Same reason: the platform checks the terrain it would phase
            # through every tick, and that check was a full scan of every
            # collision tile in the level.
            platform.spatial_hash = self.spatial_hash

        # Systems assembled by the level (audit F1.2/§4): the level owns them
        # and re-exposes the state they hold, while the gameplay loop owns the
        # order in which they run (audit F1.6).  Each one takes its
        # collaborators explicitly, so it stays independently testable.
        # P4.1: one ContactSystem instance shared by all four offensive
        # producers (melee via GameplayLoop, projectiles, hazards, contact).
        self.contact_system = ContactSystem()
        self.platform_system = PlatformSystem(self.groups, self.spatial_hash)
        self.physics_system = PhysicsSystem(self.groups)
        self.hazard_system = HazardSystem(self.groups)
        self.contact_damage_system = ContactDamageSystem(contact_system=self.contact_system)
        self.hazard_damage_system = HazardDamageSystem(contact_system=self.contact_system)
        self.respawn_system = PlayerRespawnSystem(self.player, level_data)
        self.progression_system = ProgressionSystem(self.groups.exit_sprites)
        self.camera_system = CameraSystem(self.camera)
        self.notification_system = NotificationSystem(events, level_id, level_data)
        self.tick_system = TickSystem()
        self.projectile_system = ProjectileSystem(
            self.groups,
            spatial_hash=self.spatial_hash,
            contact_system=self.contact_system,
        )
        # Assembled after the projectile system so it can be *given* rather
        # than assigned in afterwards. It used to be created before the world
        # build and handed its projectile system as an attribute write a few
        # lines later, which contradicted the "collaborators are injected
        # explicitly" claim the rest of this constructor is built on: an object
        # that is half-configured for the first third of its life can be used
        # in that state, and nothing said so. Nothing needs the spawner
        # during the build -- it was only ever ordered early because of the
        # spatial hash it shares, which is created above.
        self.spawn_system = SpawnSystem(
            self.groups,
            self.spatial_hash,
            projectile_system=self.projectile_system,
        )

        self.gameplay_loop = GameplayLoop(
            platform_system=self.platform_system,
            physics_system=self.physics_system,
            hazard_system=self.hazard_system,
            contact_damage_system=self.contact_damage_system,
            hazard_damage_system=self.hazard_damage_system,
            respawn_system=self.respawn_system,
            progression_system=self.progression_system,
            spawn_system=self.spawn_system,
            camera_system=self.camera_system,
            notification_system=self.notification_system,
            tick_system=self.tick_system,
            projectile_system=self.projectile_system,
            contact_system=self.contact_system,
        )

        if self.events is not None:
            self.events.emit(LevelStarted(level_id=self.level_id))

    def _install_static_culls(self) -> None:
        """Hand the renderer a chunked cull for the frozen tile planes.

        The index is only correct if the plane it holds is genuinely frozen.
        A sprite that moves after being indexed is culled against the
        rectangle it had when the index was built, which drops it off screen
        or leaves it behind, and either way it is a wrong frame with no error
        anywhere. The world builder only ever files tile layers here, but a
        factory that registered a moving sprite would not be caught by
        reading that code, so the moving planes are checked instead: if one
        of them turns up in the frozen plane, the index is not installed and
        the level draws exactly as it did before.
        """
        statics = self.groups.static_sprites
        if not statics:
            return
        static_ids = frozenset(id(sprite) for sprite in statics)
        if any(id(sprite) in static_ids for plane in self._moving_planes() for sprite in plane):
            logger.warning(
                "A moving sprite is registered in the frozen tile plane; the "
                "chunked cull would judge it against a stale rectangle, so the "
                "linear cull is kept."
            )
            return
        foreground = TileChunkIndex(self.groups.fg_sprites) if self.groups.fg_sprites else None
        self.renderer.set_static_planes(TileChunkIndex(statics), foreground)

    def _moving_planes(self) -> tuple[Iterable[Any], ...]:
        """The sprite groups whose contents move during a session."""
        groups = self.groups
        return (
            groups.entity_sprites,
            groups.hazard_sprites,
            groups.moving_platforms,
            groups.projectile_sprites,
            groups.exit_sprites,
            groups.combat_sprites,
        )

    @property
    def respawn_timer(self) -> float:
        """Respawn countdown in seconds, owned by the respawn system."""
        return self.respawn_system.respawn_timer

    @respawn_timer.setter
    def respawn_timer(self, value: float) -> None:
        self.respawn_system.respawn_timer = value

    @property
    def deaths(self) -> int:
        """Number of respawns performed, owned by the respawn system.

        ``GameplayScene`` turns this into a Game Over transition after
        ``Gameplay.MAX_DEATHS`` (Phase 2 #4).
        """
        return self.respawn_system.deaths

    @deaths.setter
    def deaths(self, value: int) -> None:
        self.respawn_system.deaths = value

    @property
    def exit_reached(self) -> bool:
        """True once the player touched the exit, owned by progression."""
        return self.progression_system.exit_reached

    @exit_reached.setter
    def exit_reached(self, value: bool) -> None:
        self.progression_system.exit_reached = value

    @property
    def completed(self) -> bool:
        """Return True if the player has reached the level exit flag."""
        return self.exit_reached

    def update(self, delta_time: float) -> None:
        """
        Advance the level simulation by one tick.

        The level is a strict facade (audit F1.2/§4): the whole tick —
        debug spawner, every simulation stage, camera follow, event-bus
        notifications and the end-of-tick rollback snapshot — runs inside
        the gameplay loop's pipeline.
        """
        self.gameplay_loop.update(delta_time, self.groups, self.player, self, self.rollback)
        if Debug.is_enabled():
            renderer = getattr(self, "renderer", None)
            if renderer is not None:
                renderer.overlay.update_metrics(self.gameplay_loop.contact_system.tick_metrics)

    def save_state(self) -> LevelSnapshot:
        """Capture the whole level's simulation state for rollback (Phase 3 #3).

        Groups the per-entity snapshots (keyed by deterministic ``entity_id``)
        with the level's own transient state and the moving-platform
        kinematics.  The entity grid and camera are *derived* state — rebuilt
        from entity positions / player position — so they are not captured.
        """
        entities: dict[str, EntitySnapshot] = {}
        for entity in self.groups.entity_sprites:
            save = getattr(entity, "save_state", None)
            if save is None:
                continue
            snapshot = save()
            entities[snapshot.entity_id] = snapshot

        platforms = [
            PlatformSnapshot(
                platform=platform,
                pos=(platform.pos.x, platform.pos.y),
                current_target=platform.current_target,
                direction=platform.direction,
            )
            for platform in self.groups.moving_platforms
        ]

        input_current, input_previous = self.input_manager.snapshot()
        return LevelSnapshot(
            tick=self.tick,
            hit_stop_timer=self.gameplay_loop.combat_system.hit_stop_timer,
            respawn_timer=self.respawn_timer,
            deaths=self.deaths,
            exit_reached=self.exit_reached,
            player_dead_emitted=self.notification_system.player_dead_emitted,
            completed_emitted=self.notification_system.completed_emitted,
            input_current=input_current,
            input_previous=input_previous,
            entities=entities,
            platforms=platforms,
        )

    def load_state(self, snapshot: LevelSnapshot) -> None:
        """Rewind the level to a captured tick.

        Repairs the live sprite groups as it restores: entities absent from
        the snapshot (spawned later) are reaped, and entities killed since
        capture are re-added to their recorded groups before their state is
        loaded.  The entity grid is left untouched — it is rebuilt from
        entity positions at the start of the next tick.
        """
        self.tick = snapshot.tick
        self.gameplay_loop.combat_system.hit_stop_timer = snapshot.hit_stop_timer
        self.respawn_timer = snapshot.respawn_timer
        self.deaths = snapshot.deaths
        self.exit_reached = snapshot.exit_reached
        self.notification_system.player_dead_emitted = snapshot.player_dead_emitted
        self.notification_system.completed_emitted = snapshot.completed_emitted
        self.input_manager.restore_snapshot(snapshot.input_current, snapshot.input_previous)

        # Reap entities that did not exist at capture time (e.g. a debug
        # spawn after the target tick) — they must not pollute the restored
        # simulation.  Only snapshottable entities are candidates: a plain
        # sprite without ``save_state`` was never captured and must stay.
        for entity in list(self.groups.entity_sprites):
            if not hasattr(entity, "save_state"):
                continue
            if getattr(entity, "id", None) not in snapshot.entities:
                entity.kill()

        for entity_snapshot in snapshot.entities.values():
            entity = entity_snapshot.entity
            if entity not in self.groups.entity_sprites:
                entity.add(*entity_snapshot.groups)
            entity.load_state(entity_snapshot)

        for platform_snapshot in snapshot.platforms:
            platform = platform_snapshot.platform
            platform.pos.x, platform.pos.y = platform_snapshot.pos
            platform.current_target = platform_snapshot.current_target
            platform.direction = platform_snapshot.direction
            platform.rect.topleft = platform.pos
            platform.hitbox.topleft = platform.pos
            platform.old_rect = platform.rect.copy()
            platform.old_hitbox = platform.hitbox.copy()

    def draw(
        self,
        fps: float,
        scene_host: SceneHost | None = None,
        frame_time: float = 0.0,
        alpha: float = 0.0,
    ) -> None:
        """
        Render the level and all overlays into the render target.

        Args:
            fps: Current frames per second, used for debug display.
            scene_host: Whoever can say which scene is on top, for the
                debug SCENE panel. None draws the level without it.
            frame_time: Last frame duration in ms (debug PERFORMANCE panel).
            alpha: Position within the pending simulation tick, in [0, 1].
        """
        debug_enabled = Debug.is_enabled()
        self.renderer.draw(self.groups, debug_enabled, dt=frame_time / 1000.0, alpha=alpha)
        # Painted after the world pass, over it. Nothing has to be declared or
        # merged: the next frame erases the whole target, so a bar that moves or
        # vanishes cannot leave anything behind.
        self.renderer.draw_health_bars(self.groups.entity_sprites)
        for event in self.gameplay_loop.combat_system.guard_events:
            if event.kind == "clash":
                self.renderer.overlay.note_clash(self.gameplay_loop.combat_system.last_clash)
        self.renderer.overlay.draw_metrics_panel(
            player=self.player,
            hit_stop=self.gameplay_loop.combat_system.hit_stop_timer,
        )

        if not debug_enabled:
            return

        # Bars painted over the debug overlays: stamp the clash ring again so
        # a clash never hides behind an HP bar (this stamp spends no TTL).
        self.renderer.overlay.stamp_clash_marker(self.renderer.camera)
        self.renderer.draw_debug_panels(
            player=self.player,
            fps=fps,
            sprite_count=len(self.groups.static_sprites)
            + len(self.groups.all_sprites)
            + len(self.groups.fg_sprites),
            combat_count=len(self.groups.combat_sprites),
            entity_count=len(self.groups.entity_sprites),
            collision_count=len(self.groups.collision_sprites),
            hit_stop=self.gameplay_loop.combat_system.hit_stop_timer,
            spawn_cooldown=self.spawn_system.spawn_cooldown_max,
            scene_host=scene_host,
            frame_time=frame_time,
        )
