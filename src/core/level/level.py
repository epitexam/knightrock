"""
The Level facade: it builds a world and delegates its tick to the systems.
"""

from typing import Any

import pygame

from src.application.events import EventBus, LevelStarted
from src.core.level.level_data import LevelData
from src.core.level.systems.camera_system import CameraSystem
from src.core.level.systems.contact_damage import ContactDamageSystem
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
from src.core.rendering.renderer import Renderer
from src.core.rollback import LevelSnapshot, PlatformSnapshot, RollbackSystem
from src.core.settings import Debug, Display
from src.core.sprite_groups import SpriteGroups
from src.data.provider import GameplayData
from src.entities.entity import EntitySnapshot
from src.entities.player import Player
from src.physics.spatial_hash import SpatialHash


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
        display_surface: pygame.Surface,
        level_data: LevelData,
        input_manager,
        level_id: int = 0,
        events: EventBus | None = None,
        rollback_enabled: bool = False,
        gameplay_data: GameplayData | None = None,
    ) -> None:
        """
        Initialize the level from parsed TMX data and build the world.

        Args:
            display_surface: The Pygame surface to draw on.
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
        self.display_surface = display_surface
        self.input_manager = input_manager
        self.level_data = level_data

        self.groups = SpriteGroups()

        self.camera = Camera(Display.WIDTH, Display.HEIGHT)
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

        self.renderer = Renderer(self.display_surface, self.camera, level_data.config)
        # Spatial hash for O(1) collision lookups (PERF-01/02): created before
        # the spawner so runtime-spawned enemies join the grid too.
        self.spatial_hash = SpatialHash(cell_size=128)
        self.spawn_system = SpawnSystem(self.groups, self.spatial_hash)

        self.world_builder = WorldBuilder(level_data, gameplay_data)
        self.player: Player = self.world_builder.build(self.groups, self.input_manager)

        # Bucket the static collidables once; entities query the grid every
        # tick, so each one must know it (moving platforms are re-bucketed
        # each tick by PlatformSystem).
        self.spatial_hash.add_all(self.groups.collision_sprites)
        for entity in self.groups.entity_sprites:
            entity.spatial_hash = self.spatial_hash

        # Systems assembled by the level (audit F1.2/§4): the level owns them
        # and re-exposes the state they hold, while the gameplay loop owns the
        # order in which they run (audit F1.6).  Each one takes its
        # collaborators explicitly, so it stays independently testable.
        self.platform_system = PlatformSystem(self.groups, self.spatial_hash)
        self.physics_system = PhysicsSystem(self.groups)
        self.hazard_system = HazardSystem(self.groups)
        self.contact_damage_system = ContactDamageSystem()
        self.hazard_damage_system = HazardDamageSystem()
        self.respawn_system = PlayerRespawnSystem(self.player, level_data)
        self.progression_system = ProgressionSystem(self.groups.exit_sprites)
        self.camera_system = CameraSystem(self.camera)
        self.notification_system = NotificationSystem(events, level_id, level_data)
        self.tick_system = TickSystem()
        self.projectile_system = ProjectileSystem(self.groups, spatial_hash=self.spatial_hash)
        self.spawn_system.projectile_system = self.projectile_system

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
        )

        if self.events is not None:
            self.events.emit(LevelStarted(level_id=self.level_id))

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

    @property
    def slowmo_scale(self) -> float:
        """Real-time scale for the Game loop (kill slow-motion dip)."""
        return self.gameplay_loop.combat_system.slowmo_scale

    def update(self, delta_time: float) -> None:
        """
        Advance the level simulation by one tick.

        The level is a strict facade (audit F1.2/§4): the whole tick —
        debug spawner, every simulation stage, camera follow, event-bus
        notifications and the end-of-tick rollback snapshot — runs inside
        the gameplay loop's pipeline.
        """
        self.gameplay_loop.update(delta_time, self.groups, self.player, self, self.rollback)

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

        return LevelSnapshot(
            tick=self.tick,
            hit_stop_timer=self.gameplay_loop.combat_system.hit_stop_timer,
            respawn_timer=self.respawn_timer,
            deaths=self.deaths,
            exit_reached=self.exit_reached,
            player_dead_emitted=self.notification_system.player_dead_emitted,
            completed_emitted=self.notification_system.completed_emitted,
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
        game: Any = None,
        frame_time: float = 0.0,
    ) -> list[pygame.Rect] | None:
        """
        Render the level and all overlays.

        Returns the dirty screen rects to present, or ``None`` when the
        whole display must be refreshed (debug mode draws panels over the
        full screen).

        Args:
            fps: Current frames per second, used for debug display.
            game: The Game instance (used by the debug SCENE panel).
            frame_time: Last frame duration in ms (debug PERFORMANCE panel).
        """
        debug_enabled = Debug.is_enabled()
        dirty: list[pygame.Rect] | None = self.renderer.draw(
            self.groups, debug_enabled, dt=frame_time / 1000.0
        )
        self.renderer.draw_health_bars(self.groups.entity_sprites)

        if not debug_enabled:
            return dirty

        self.renderer.draw_debug_panels(
            player=self.player,
            fps=fps,
            sprite_count=len(self.groups.all_sprites),
            combat_count=len(self.groups.combat_sprites),
            entity_count=len(self.groups.entity_sprites),
            collision_count=len(self.groups.collision_sprites),
            hit_stop=self.gameplay_loop.combat_system.hit_stop_timer,
            spawn_cooldown=self.spawn_system.spawn_cooldown_max,
            game=game,
            frame_time=frame_time,
        )
        return None
