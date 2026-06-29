from src.core.colors import Colors
from src.ui.ui_manager import UIManager


class Renderer:
    def __init__(self, display_surface, camera):
        self.display_surface = display_surface
        self.camera = camera
        self.ui_manager = UIManager(display_surface)

    def draw(self, all_sprites, debug_enabled=False):
        self.display_surface.fill(Colors.red)
        for sprite in all_sprites:
            rect = self.camera.apply(sprite.rect)
            self.display_surface.blit(sprite.image, rect)

        if debug_enabled:
            self.ui_manager.draw_debug_overlays(all_sprites, self.camera)

    def draw_health_bars(self, entities):
        """Draw the health bars for the entities (player, enemies)."""
        self.ui_manager.draw_health_bars(entities, self.camera)

    def draw_debug_panels(self, player, fps, sprite_count, combat_count,
                          entity_count, collision_count, hit_stop, spawn_cd):
        x, y = 10, 10
        y += self.ui_manager.draw_state_panel(x, y, player) + 8
        self.ui_manager.draw_stats_panel(x, y, player)
        self.ui_manager.draw_performance_panel(
            fps=fps,
            sprite_count=sprite_count,
            combat_count=combat_count,
            entity_count=entity_count,
            collision_count=collision_count,
            hit_stop=hit_stop,
            spawn_cd=spawn_cd,
        )