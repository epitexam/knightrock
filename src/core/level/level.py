"""
Level class orchestrating the game world, entities, and simulation loop.
"""

from typing import Any

import pygame

from src.application.events import EventBus, LevelCompleted, LevelStarted, PlayerDied
from src.core.gameplay.debug_controller import DebugController
from src.core.gameplay.gameplay_loop import GameplayLoop
from src.core.level.level_data import LevelData
from src.core.level.world_builder import WorldBuilder
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.rollback import LevelSnapshot, PlatformSnapshot, RollbackSystem
from src.core.settings import Debug, Display, Respawn
from src.core.sprite_groups import SpriteGroups
from src.entities.entity import EntitySnapshot
from src.entities.player import Player
from src.physics.contact_damage import ContactDamageSystem
from src.physics.hazard_damage import HazardDamageSystem
from src.physics.movement import apply_moving_platform
from src.physics.spatial_hash import SpatialHash


class Level:
    """
    Manages a single game level, including its entities, physics, combat,
    camera, and rendering.

    The level owns all sprite groups, the camera, the gameplay loop,
    and the debug controller. It processes updates and rendering each frame.
    """

    def __init__(
        self,
        display_surface: pygame.Surface,
        level_data: LevelData,
        input_manager,
        level_id: int = 0,
        events: EventBus | None = None,
        rollback_enabled: bool = False,
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
        """
        self.display_surface = display_surface
        self.input_manager = input_manager
        self.level_data = level_data

        self.groups = SpriteGroups()

        self.camera = Camera(Display.WIDTH, Display.HEIGHT)
        self.camera.set_world_size(level_data.pixel_width, level_data.pixel_height)

        self.exit_reached = False
        self.respawn_timer = 0.0
        # Number of respawns performed; GameplayScene turns this into a
        # Game Over transition after Gameplay.MAX_DEATHS (Phase 2 #4).
        self.deaths = 0
        self.level_id = level_id
        self.events = events
        self._player_dead_emitted = False
        self._completed_emitted = False

        # Local rollback core (Phase 3 #3): monotonic fixed-tick counter and
        # the ring buffer that captures a snapshot at the end of each tick.
        # Recording is opt-in because a capture costs a full state copy.
        self.tick = 0
        self.rollback_enabled = rollback_enabled
        self.rollback = RollbackSystem()

        self.gameplay_loop = GameplayLoop()
        self.renderer = Renderer(self.display_surface, self.camera, level_data.config)
        # Spatial hash for O(1) collision lookups (PERF-01/02): created before
        # the debug controller so runtime-spawned enemies join the grid too.
        self.spatial_hash = SpatialHash(cell_size=128)
        self.debug_controller = DebugController(self.groups, self.spatial_hash)
        self.contact_damage_system = ContactDamageSystem()
        self.hazard_damage_system = HazardDamageSystem()

        self.world_builder = WorldBuilder(level_data)
        self.player: Player = self.world_builder.build(self.groups, self.input_manager)

        # Bucket the static collidables once; entities query the grid every
        # tick, so each one must know it (moving platforms are re-bucketed
        # per tick in update()).
        self.spatial_hash.add_all(self.groups.collision_sprites)
        for entity in self.groups.entity_sprites:
            entity.spatial_hash = self.spatial_hash

        if self.events is not None:
            self.events.emit(LevelStarted(level_id=self.level_id))

    @property
    def completed(self) -> bool:
        """Return True if the player has reached the level exit flag."""
        return self.exit_reached

    def update(self, delta_time: float) -> None:
        """
        Advance the level simulation by one tick.

        Handles hit-stop, moving platforms, hazards, entity updates,
        combat, contact damage, respawning, camera follow, and exit detection.
        """
        self.debug_controller.update(delta_time, self.player)

        effective_delta = self.gameplay_loop.begin_tick(delta_time)

        if effective_delta > 0.0:
            self.groups.moving_platforms.update(effective_delta)
            # Platforms moved this tick: re-bucket them so entity collision
            # queries keep finding them at their current position (PERF-01).
            self.spatial_hash.update_all(self.groups.moving_platforms)
            self.groups.hazard_sprites.update(effective_delta)

            for entity in self.groups.entity_sprites:
                apply_moving_platform(entity, self.groups.moving_platforms)

            self.groups.entity_sprites.update(effective_delta)
            self.groups.fx_sprites.update(effective_delta)

            self.gameplay_loop.process_combat_and_separation(
                effective_delta,
                self.groups.combat_sprites,
                self.groups.entity_sprites,
            )
            self.contact_damage_system.process(
                self.groups.entity_sprites, self.gameplay_loop.entity_grid
            )
            self.hazard_damage_system.process(
                self.groups.entity_sprites, self.groups.hazard_sprites
            )
            self.gameplay_loop.remove_dead_entities(self.groups.entity_sprites, self.player)

            if self.player.is_dead:
                self.respawn_timer += effective_delta
                if self.respawn_timer >= Respawn.DELAY_S:
                    self.player.respawn()
                    self.respawn_timer = 0.0
                    self.deaths += 1
            else:
                self.respawn_timer = 0.0

            # Check for death by falling below the death border (BUG-06)
            if (
                self.player.hitbox.top > self.level_data.config.death_border_bottom
                and self.level_data.config.death_border_bottom > 0
            ):
                self.player.die()

            if not self.player.is_dead and pygame.sprite.spritecollide(
                self.player, self.groups.exit_sprites, False
            ):
                self.exit_reached = True

        if not self.player.is_dead:
            self.camera.follow(self.player.hitbox, delta_time)

        self._emit_notifications()

        # One snapshot per fixed tick, recorded even when hit-stop suspended
        # the simulation (the hit-stop timer itself advances every tick), so
        # ``rollback_to(tick)`` restores the exact end-of-tick world state.
        if self.rollback_enabled:
            self.rollback.record(self)
        self.tick += 1

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
            player_dead_emitted=self._player_dead_emitted,
            completed_emitted=self._completed_emitted,
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
        self._player_dead_emitted = snapshot.player_dead_emitted
        self._completed_emitted = snapshot.completed_emitted

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

    def _emit_notifications(self) -> None:
        """Publish bus events for the app layer (never mutates simulation)."""
        if self.events is None:
            return

        if self.player.is_dead and not self._player_dead_emitted:
            self._player_dead_emitted = True
            self.events.emit(PlayerDied(entity_id=self.player.id, deaths=self.deaths))
        elif not self.player.is_dead:
            self._player_dead_emitted = False

        if self.exit_reached and not self._completed_emitted:
            self._completed_emitted = True
            self.events.emit(
                LevelCompleted(
                    level_id=self.level_id,
                    unlock_level_id=self.level_data.config.level_unlock,
                )
            )

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
        dirty: list[pygame.Rect] | None = self.renderer.draw(self.groups, debug_enabled)
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
            spawn_cooldown=self.debug_controller.spawn_cooldown_max,
            game=game,
            frame_time=frame_time,
        )
        return None
