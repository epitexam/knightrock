from typing import Optional

from src.core.colors import Colors
from src.core.sprite_groups import SpriteGroups
from src.core.level.level_data import LevelConfig
from src.ui.ui_manager import UIManager


class Renderer:
    def __init__(self, display_surface, camera, config: Optional[LevelConfig] = None):
        self.display_surface = display_surface
        self.camera = camera
        self.ui_manager = UIManager(display_surface)
        self.background_color = self._resolve_background_color(config)

    @staticmethod
    def _resolve_background_color(config):
        if config is not None and config.bg:
            color = getattr(Colors, config.bg, None)
            if color is not None:
                return color
        return Colors.red

    def draw(self, groups: SpriteGroups, debug_enabled: bool = False) -> None:
        self.display_surface.fill(self.background_color)

        for sprite in groups.all_sprites:
            rect = self.camera.apply(sprite.rect)
            self.display_surface.blit(sprite.image, rect)

        for sprite in groups.fg_sprites:
            rect = self.camera.apply(sprite.rect)
            self.display_surface.blit(sprite.image, rect)

        if debug_enabled:
            self.ui_manager.draw_debug_overlays(groups.all_sprites, self.camera)

    def draw_health_bars(self, entities) -> None:
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