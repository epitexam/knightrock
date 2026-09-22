from typing import Any

import pygame

from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelLayout, PanelRenderer
from src.ui.player_ui import PlayerUI
from src.ui.styles import TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN
from src.ui.world_ui import WorldUI


class UIManager:
    """Facade pattern for the user interface."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        self.renderer = PanelRenderer(display_surface)
        self.player_ui = PlayerUI(self.renderer)
        self.world_ui = WorldUI(self.renderer)

    def draw_state_panel(
        self, x: int, y: int, player: Any, layout: PanelLayout | None = None
    ) -> int:
        return self.player_ui.draw_state_panel(x, y, player, layout=layout)

    def draw_stats_panel(
        self, x: int, y: int, player: Any, layout: PanelLayout | None = None
    ) -> int:
        return self.player_ui.draw_stats_panel(x, y, player, layout=layout)

    def draw_scene_panel(self, x: int, y: int, game: Any, layout: PanelLayout | None = None) -> int:
        """Show active scene, current level, deaths and live entity counts."""
        current = game.scene_manager.current
        scene_name = type(current).__name__ if current else "None"

        level_id = getattr(current, "level_id", None)
        deaths = getattr(current, "level", None)
        deaths_n = deaths.deaths if deaths is not None else 0
        level_str = str(level_id) if level_id is not None else "-"

        lines = [
            f"Scene   {scene_name}",
            f"Level   {level_str}   deaths {deaths_n}",
        ]

        # Entity counts are only meaningful while a level is live.
        level = getattr(current, "level", None) if current is not None else None
        if level is not None:
            lines.append(
                f"Entities {len(level.groups.entity_sprites)}"
                f"  enemies {len([e for e in level.groups.entity_sprites if getattr(e, 'faction', None) == 'enemy'])}"
            )
            lines.append(f"Hazards  {len(level.groups.hazard_sprites)}")
            projectiles = getattr(level.groups, "projectile_sprites", None)
            if projectiles is not None:
                lines.append(f"Shots    {len(projectiles)}")

        return self.renderer.draw_panel(x, y, lines, title="SCENE", layout=layout)

    def draw_help_panel(
        self, x: int, y: int, layout: PanelLayout | None = None, layers: dict[str, bool] | None = None
    ) -> int:
        """List the debug test-bench keys and overlay toggles."""
        states = layers or {}

        def mark(key: str) -> str:
            if key not in states:
                return ""
            return " [ON]" if states[key] else " [OFF]"

        lines = [
            "1-4  test attacks",
            "V/B  firebolt / pierce",
            "C    juggle dummy",
            "G/P/T spawn foe",
            f"F1   boxes{mark('boxes')}",
            f"F2   labels{mark('labels')}",
            f"F3   velocities{mark('velocities')}",
            f"F4   statics{mark('statics')}",
            f"F5   panels{mark('panels')}",
            "F6   freeze (debug)",
            "F7   step (frozen)",
        ]
        return self.renderer.draw_panel(x, y, lines, title="DEBUG KEYS", layout=layout)

    def draw_legend_panel(self, x: int, y: int, layout: PanelLayout | None = None) -> int:
        """Persistent color legend for the world-space combat overlay."""
        from src.ui.world_ui import PHASE_OUTLINE_COLORS

        lines = [
            "blue/red  pushbox (player/foe)",
            "green     hurtbox / zones",
            "orange    attack active",
            "gold      attack startup",
            "grey      attack recovery",
            "dashed    sweep ghost",
            "P2/UBL    priority/unblockable",
            "cyan      OTG guard",
            "purple    juggle gravity",
        ]
        line_colors = {
            2: PHASE_OUTLINE_COLORS["active"],
            3: PHASE_OUTLINE_COLORS["startup"],
            4: PHASE_OUTLINE_COLORS["recovery"],
        }
        return self.renderer.draw_panel(
            x, y, lines, title="LEGEND", layout=layout, text_color=TEXT_MUTED, line_colors=line_colors
        )

    def draw_performance_panel(
        self,
        fps: float,
        sprite_count: int,
        combat_count: int,
        entity_count: int,
        collision_count: int,
        hit_stop: float,
        spawn_cooldown: float,
        frame_time: float = 0.0,
        cache_size: int = 0,
        layout: PanelLayout | None = None,
    ) -> None:
        fps_color = TEXT_OK if fps >= 55 else TEXT_WARN if fps >= 30 else TEXT_CRIT
        frame_color = TEXT_OK if frame_time <= 18 else TEXT_WARN if frame_time <= 33 else TEXT_CRIT
        lines = [
            f"FPS        {fps:5.1f}",
            f"Frame      {frame_time:5.1f} ms",
            f"Sprites    {sprite_count}",
            f"Combat     {combat_count}",
            f"Entities   {entity_count}",
            f"Collision  {collision_count}",
            f"Cache      {cache_size}",
            f"Hit Stop   {hit_stop:.3f}",
            f"Spawn CD   {spawn_cooldown:.3f}",
        ]

        panel_w = self.renderer.get_panel_width(lines)
        if layout is not None:
            panel_w, panel_h = self.renderer.measure_panel(lines, title="PERFORMANCE")
            panel_x, panel_y = layout.place_top_right(panel_w, panel_h)
        else:
            panel_x = self.renderer.display_surface.get_width() - panel_w - 12
            panel_y = 12

        self.renderer.draw_panel(
            panel_x,
            panel_y,
            lines,
            title="PERFORMANCE",
            line_colors={0: fps_color, 1: frame_color},
        )

    def draw_debug_overlays(self, all_sprites: pygame.sprite.Group, camera: Camera) -> None:
        self.world_ui.draw_debug_overlays(all_sprites, camera)

    def draw_health_bars(self, entities: pygame.sprite.Group | list, camera: Camera) -> None:
        self.world_ui.draw_health_bars(entities, camera)
