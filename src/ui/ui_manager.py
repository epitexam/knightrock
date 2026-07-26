import pygame
from typing import Any
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.player_ui import PlayerUI
from src.ui.world_ui import WorldUI
from src.ui.styles import TEXT_MUTED, TEXT_WARN, TEXT_CRIT, TEXT_OK


class UIManager:
    """Fait office de Façade (Facade pattern) pour l'Interface Utilisateur."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        self.renderer = PanelRenderer(display_surface)
        self.player_ui = PlayerUI(self.renderer)
        self.world_ui = WorldUI(self.renderer)

    def draw_state_panel(self, x: int, y: int, player: Any) -> int:
        return self.player_ui.draw_state_panel(x, y, player)

    def draw_stats_panel(self, x: int, y: int, player: Any) -> int:
        return self.player_ui.draw_stats_panel(x, y, player)

    def draw_performance_panel(
        self, fps: float, sprite_count: int, combat_count: int,
        entity_count: int, collision_count: int, hit_stop: float, spawn_cd: float
    ) -> None:
        fps_color = TEXT_OK if fps >= 55 else TEXT_WARN if fps >= 30 else TEXT_CRIT
        lines = [
            f"FPS        {fps:5.1f}",
            f"Sprites    {sprite_count}",
            f"Combat     {combat_count}",
            f"Entities   {entity_count}",
            f"Collision  {collision_count}",
            f"Hit Stop   {hit_stop:.3f}",
            f"Spawn CD   {spawn_cd:.3f}",
        ]

        panel_w = self.renderer.get_panel_width(lines)
        panel_x = self.renderer.display_surface.get_width() - panel_w - 12

        self.renderer.draw_panel(
            panel_x, 12, lines, title="PERFORMANCE", line_colors={0: fps_color})

    def draw_debug_overlays(self, all_sprites: pygame.sprite.Group, camera: Camera) -> None:
        self.world_ui.draw_debug_overlays(all_sprites, camera)

    def draw_health_bars(self, entities: pygame.sprite.Group | list, camera: Camera) -> None:
        self.world_ui.draw_health_bars(entities, camera)
