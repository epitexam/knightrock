import pygame
from src.core.level_components import (
    WorldBuilder,
    GameplayLoop,
    Renderer,
    DebugController,
)
from src.core.settings import Display, Debug
from src.core.camera import Camera


class Level:
    def __init__(self, display_surface, tmx_map, input_manager):
        self.display_surface = display_surface
        self.input_manager = input_manager

        self.all_sprites = pygame.sprite.Group()
        self.collision_sprites = pygame.sprite.Group()
        self.moving_platforms = pygame.sprite.Group()
        self.combat_sprites = pygame.sprite.Group()
        self.entity_sprites = pygame.sprite.Group()

        self.camera = Camera(Display.WIDTH, Display.HEIGHT)

        self.player = None
        self.respawn_timer = 0.0

        self.gameplay_loop = GameplayLoop()
        self.renderer = Renderer(self.display_surface, self.camera)
        self.debug_controller = DebugController(
            self.all_sprites,
            self.collision_sprites,
            self.combat_sprites,
            self.entity_sprites,
        )

        self.setup(tmx_map)

    def setup(self, tmx_map):
        self.world_builder = WorldBuilder(tmx_map)
        self.player = self.world_builder.build(
            self.all_sprites,
            self.collision_sprites,
            self.moving_platforms,
            self.combat_sprites,
            self.entity_sprites,
            self.input_manager,
        )

    def update(self, delta_time: float) -> None:
        self.debug_controller.update(delta_time, self.player)

        if not self.gameplay_loop.combat_system.in_hit_stop:
            self.all_sprites.update(delta_time)

        self.gameplay_loop.process_combat_and_separation(
            delta_time, self.combat_sprites, self.entity_sprites
        )
        self.gameplay_loop.remove_dead_entities(self.entity_sprites, self.player)

        if self.player is not None and self.player.is_dead:
            self.respawn_timer += delta_time
            if self.respawn_timer >= 2.0:
                self.player.respawn()
                self.respawn_timer = 0.0
        else:
            self.respawn_timer = 0.0

        if self.player is not None and not self.player.is_dead:
            self.camera.follow(self.player.hitbox)

    def draw(self, fps: float) -> None:
        self.renderer.draw(self.all_sprites, Debug.ENABLED)

        if Debug.ENABLED:
            self.renderer.draw_debug_panels(
                player=self.player,
                fps=fps,
                sprite_count=len(self.all_sprites),
                combat_count=len(self.combat_sprites),
                entity_count=len(self.entity_sprites),
                collision_count=len(self.collision_sprites),
                hit_stop=self.gameplay_loop.combat_system.hit_stop_timer,
                spawn_cd=self.debug_controller.spawn_cooldown,
            )