"""
Level class orchestrating the game world, entities, and simulation loop.
"""

import pygame

from src.core.level.world_builder import WorldBuilder
from src.core.gameplay.gameplay_loop import GameplayLoop
from src.core.rendering.renderer import Renderer
from src.core.gameplay.debug_controller import DebugController
from src.core.settings import Display, Debug
from src.core.rendering.camera import Camera
from src.core.sprite_groups import SpriteGroups
from src.core.level.level_data import LevelData
from src.physics.contact_damage import ContactDamageSystem
from src.physics.movement import apply_moving_platform


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
    ) -> None:
        """
        Initialise the level from parsed TMX data and build the world.

        Args:
            display_surface: The Pygame surface to draw on.
            level_data: Parsed level data containing tile layers and objects.
            input_manager: The input manager used by the player.
        """
        self.display_surface = display_surface
        self.input_manager = input_manager
        self.level_data = level_data

        self.groups = SpriteGroups()

        self.camera = Camera(Display.WIDTH, Display.HEIGHT)
        self.camera.set_world_size(
            level_data.pixel_width, level_data.pixel_height)

        self.exit_reached = False
        self.respawn_timer = 0.0

        self.gameplay_loop = GameplayLoop()
        self.renderer = Renderer(self.display_surface,
                                 self.camera, level_data.config)
        self.debug_controller = DebugController(self.groups)
        self.contact_damage_system = ContactDamageSystem()

        self.world_builder = WorldBuilder(level_data)
        self.player = self.world_builder.build(self.groups, self.input_manager)

    @property
    def completed(self) -> bool:
        """Return True if the player has reached the level exit flag."""
        return self.exit_reached

    def update(self, delta_time: float) -> None:
        """
        Advance the level simulation by one tick.

        Handles hit‑stop, moving platforms, hazards, entity updates,
        combat, contact damage, respawning, camera follow, and exit detection.
        """
        self.debug_controller.update(delta_time, self.player)

        effective_delta = self.gameplay_loop.begin_tick(delta_time)

        if effective_delta > 0.0:
            self.groups.moving_platforms.update(effective_delta)
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
            self.contact_damage_system.process(self.groups.entity_sprites)
            self.gameplay_loop.remove_dead_entities(
                self.groups.entity_sprites, self.player)

            if self.player is not None and self.player.is_dead:
                self.respawn_timer += effective_delta
                if self.respawn_timer >= 2.0:
                    self.player.respawn()
                    self.respawn_timer = 0.0
            else:
                self.respawn_timer = 0.0

            if (
                self.player is not None
                and not self.player.is_dead
                and pygame.sprite.spritecollide(
                    self.player, self.groups.exit_sprites, False
                )
            ):
                self.exit_reached = True

        if self.player is not None and not self.player.is_dead:
            self.camera.follow(self.player.hitbox, delta_time)

    def draw(self, fps: float) -> None:
        """
        Render the level and all overlays.

        Args:
            fps: Current frames per second, used for debug display.
        """
        self.renderer.draw(self.groups, Debug.ENABLED)
        self.renderer.draw_health_bars(self.groups.entity_sprites)

        if Debug.ENABLED:
            self.renderer.draw_debug_panels(
                player=self.player,
                fps=fps,
                sprite_count=len(self.groups.all_sprites),
                combat_count=len(self.groups.combat_sprites),
                entity_count=len(self.groups.entity_sprites),
                collision_count=len(self.groups.collision_sprites),
                hit_stop=self.gameplay_loop.combat_system.hit_stop_timer,
                spawn_cd=self.debug_controller.spawn_cooldown,
            )
