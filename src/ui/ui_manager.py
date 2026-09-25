from collections.abc import Iterable
from typing import Any

import pygame

from src.core.rendering.camera import Camera
from src.ui.hud import HUD
from src.ui.panel_renderer import PanelLayout, PanelRenderer
from src.ui.player_ui import PlayerUI
from src.ui.styles import TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN
from src.ui.world_ui import COMBAT_PANEL_TITLE, WorldUI

#: Stable ids of the interactive debug panels. They name the ``×``/drag state
#: kept by :class:`~src.ui.panel_renderer.PanelInteraction`, so a panel keeps
#: its closed flag and dropped position even when it moves in the draw order.
PANEL_PERFORMANCE = "performance"
PANEL_COMBAT = "combat"
PANEL_STATE = "state"
PANEL_STATS = "stats"
PANEL_SCENE = "scene"
PANEL_KEYS = "keys"
PANEL_LEGEND = "legend"


class UIManager:
    """Facade pattern for the user interface."""

    def __init__(self, display_surface: pygame.Surface) -> None:
        self.renderer = PanelRenderer(display_surface)
        self.player_ui = PlayerUI(self.renderer)
        self.world_ui = WorldUI(self.renderer)
        self.hud = HUD(self.renderer)
        self._compact_panel_focus = PANEL_STATE

    def cycle_compact_panel(self) -> str:
        order = (
            PANEL_COMBAT,
            PANEL_STATE,
            PANEL_STATS,
            PANEL_SCENE,
            PANEL_KEYS,
            PANEL_LEGEND,
        )
        for _ in order:
            self._compact_panel_focus = order[
                (order.index(self._compact_panel_focus) + 1) % len(order)
            ]
            if not self.renderer.interaction.is_closed(self._compact_panel_focus):
                break
        return self._compact_panel_focus

    def compact_panel_focus(self) -> str:
        return self._compact_panel_focus

    def draw_compact_panel(
        self,
        player: Any,
        layout: PanelLayout,
        game: Any = None,
    ) -> int:
        panel_id = self._compact_panel_focus
        if panel_id == PANEL_COMBAT:
            height = self.draw_combat_panel(layout)
            if height > 0:
                return height
            return self.renderer.draw_panel(
                10,
                10,
                ["idle"],
                title=COMBAT_PANEL_TITLE,
                layout=layout,
                panel_id=PANEL_COMBAT,
            )
        if panel_id == PANEL_STATE:
            return self.draw_state_panel(10, 10, player, layout, compact=True)
        if panel_id == PANEL_STATS:
            return self.draw_stats_panel(10, 10, player, layout, compact=True)
        if panel_id == PANEL_SCENE:
            return self.draw_scene_panel(10, 10, game, layout, compact=True)
        if panel_id == PANEL_KEYS:
            return self.draw_help_panel(10, 10, layout, self.world_ui.layers, compact=True)
        return self.draw_legend_panel(10, 10, layout, compact=True)

    def set_display_surface(self, display_surface: pygame.Surface) -> None:
        self.renderer.set_display_surface(display_surface)
        self.world_ui.display_surface = display_surface

    def set_ui_scale(self, scale: float) -> None:
        self.hud.set_scale(scale)

    def draw_state_panel(
        self,
        x: int,
        y: int,
        player: Any,
        layout: PanelLayout | None = None,
        compact: bool = False,
    ) -> int:
        return self.player_ui.draw_state_panel(
            x, y, player, layout=layout, panel_id=PANEL_STATE, compact=compact
        )

    def draw_stats_panel(
        self,
        x: int,
        y: int,
        player: Any,
        layout: PanelLayout | None = None,
        compact: bool = False,
    ) -> int:
        return self.player_ui.draw_stats_panel(
            x, y, player, layout=layout, panel_id=PANEL_STATS, compact=compact
        )

    def draw_scene_panel(
        self,
        x: int,
        y: int,
        game: Any,
        layout: PanelLayout | None = None,
        compact: bool = False,
    ) -> int:
        """Show active scene, current level, deaths and live entity counts."""
        if self.renderer.interaction.is_closed(PANEL_SCENE):
            return 0
        current = game.scene_manager.current
        scene_name = type(current).__name__ if current else "None"

        level_id = getattr(current, "level_id", None)
        deaths = getattr(current, "level", None)
        deaths_n = deaths.deaths if deaths is not None else 0
        level_str = str(level_id) if level_id is not None else "-"

        surface = self.renderer.display_surface
        lines = [
            f"Scene   {scene_name}",
            f"Level   {level_str}   deaths {deaths_n}",
            f"View    {surface.get_width()}x{surface.get_height()}",
            f"Panels  {'on' if self.world_ui.layers['panels'] else 'off'}",
            f"Cache   {self.renderer.text_cache_stats['entries']}",
        ]

        if compact:
            return self.renderer.draw_panel(
                x,
                y,
                lines,
                title="SCENE",
                layout=layout,
                panel_id=PANEL_SCENE,
            )

        # Entity counts are only meaningful while a level is live.
        level = getattr(current, "level", None) if current is not None else None
        if level is not None:
            enemy_count = sum(
                getattr(entity, "faction", None) == "enemy"
                for entity in level.groups.entity_sprites
            )
            lines.append(f"Entities {len(level.groups.entity_sprites)}  enemies {enemy_count}")
            lines.append(f"Hazards  {len(level.groups.hazard_sprites)}")
            projectiles = getattr(level.groups, "projectile_sprites", None)
            if projectiles is not None:
                lines.append(f"Shots    {len(projectiles)}")

        return self.renderer.draw_panel(
            x, y, lines, title="SCENE", layout=layout, panel_id=PANEL_SCENE
        )

    def draw_help_panel(
        self,
        x: int,
        y: int,
        layout: PanelLayout | None = None,
        layers: dict[str, bool] | None = None,
        compact: bool = False,
    ) -> int:
        """List the debug test-bench keys and overlay toggles."""
        if self.renderer.interaction.is_closed(PANEL_KEYS):
            return 0
        states = layers or {}

        def mark(key: str) -> str:
            if key not in states:
                return ""
            return " [ON]" if states[key] else " [OFF]"

        lines = [
            "1-4  showcase",
            "5    P5 shapes",
            "6    circle burst",
            "V/B  firebolt/pierce",
            "C    juggle dummy",
            "G/P/T spawn",
            f"F1   boxes{mark('boxes')}",
            f"F2   labels{mark('labels')}",
            f"F3   vectors{mark('velocities')}",
            f"F4   statics{mark('statics')}",
            f"F5   panels{mark('panels')}",
            "F6-F9 sim/debug",
            "F10   compact panel",
            "×    close · drag",
        ]
        if compact:
            lines = [
                "1-6  test attacks",
                "V/B  projectiles",
                "G/P/T spawn",
                "F1-F5 layers",
                "F6-F10 tools",
                "×    close · drag",
            ]
        return self.renderer.draw_panel(
            x, y, lines, title="DEBUG KEYS", layout=layout, panel_id=PANEL_KEYS
        )

    def draw_legend_panel(
        self, x: int, y: int, layout: PanelLayout | None = None, compact: bool = False
    ) -> int:
        """Persistent color legend for the world-space combat overlay."""
        if self.renderer.interaction.is_closed(PANEL_LEGEND):
            return 0
        from src.core.colors import Colors
        from src.ui.world_ui import PHASE_OUTLINE_COLORS

        zone_colors = Colors.debug_hurtbox_zones
        lines = [
            "blue/red  pushbox",
            "green     hurtbox",
            "thin      plain zone",
            "fill      xmult zone",
            "dashed    guarded zone",
            "orange    attack active",
            "gold      attack startup",
            "grey      attack recovery",
            "cyan dot  broadphase",
            "violet    swept shape",
            "white +   anchor",
            "P2/UBL    hit priority",
            "purple    juggle gravity",
        ]
        if compact:
            lines = [
                "green  hurtbox",
                "orange attack active",
                "gold   startup",
                "cyan   broadphase",
                "violet swept",
                "white  anchor",
                "purple juggle",
            ]
        if compact:
            line_colors = {
                0: Colors.debug_hurtbox,
                1: PHASE_OUTLINE_COLORS["active"],
                2: PHASE_OUTLINE_COLORS["startup"],
                3: Colors.debug_broadphase,
                4: Colors.debug_sweep,
                5: Colors.debug_anchor,
                6: Colors.debug_juggle,
            }
        else:
            line_colors = {
                2: zone_colors[0],
                3: zone_colors[1],
                4: zone_colors[2],
                5: PHASE_OUTLINE_COLORS["active"],
                6: PHASE_OUTLINE_COLORS["startup"],
                7: PHASE_OUTLINE_COLORS["recovery"],
                8: Colors.debug_broadphase,
                9: Colors.debug_sweep,
                10: Colors.debug_anchor,
                12: Colors.debug_juggle,
            }
        return self.renderer.draw_panel(
            x,
            y,
            lines,
            title="LEGEND",
            layout=layout,
            text_color=TEXT_MUTED,
            line_colors=line_colors,
            panel_id=PANEL_LEGEND,
        )

    def draw_combat_panel(self, layout: PanelLayout | None = None) -> int:
        """Unified COMBAT counters inside the debug panel flow.

        The lines are collected by :meth:`WorldUI.draw_metrics_panel` (a
        no-op when ``DEBUG`` is off); drawing them through the column flow
        keeps them under the side panels instead of a fixed spot that other
        panels could stack on.
        """
        if self.renderer.interaction.is_closed(PANEL_COMBAT):
            return 0
        content = self.world_ui.combat_panel()
        if content is None:
            return 0
        title, lines = content
        assert title == COMBAT_PANEL_TITLE
        return self.renderer.draw_panel(
            10,
            10,
            [text for text, _ in lines],
            title=title,
            layout=layout,
            panel_id=PANEL_COMBAT,
            line_colors=dict(enumerate(color for _, color in lines)),
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
        cache_size: int | None = None,
        layout: PanelLayout | None = None,
        debug_stats: dict[str, float] | None = None,
    ) -> None:
        if self.renderer.interaction.is_closed(PANEL_PERFORMANCE):
            return
        fps_color = TEXT_OK if fps >= 55 else TEXT_WARN if fps >= 30 else TEXT_CRIT
        frame_color = TEXT_OK if frame_time <= 18 else TEXT_WARN if frame_time <= 33 else TEXT_CRIT
        cache_stats = self.renderer.text_cache_stats
        entries = cache_stats["entries"] if cache_size is None else cache_size
        cache_total = cache_stats["hits"] + cache_stats["misses"]
        cache_hit_rate = 100.0 * cache_stats["hits"] / cache_total if cache_total else 100.0
        timing = debug_stats or {}
        world_ms = float(timing.get("world_ui_ms", 0.0))
        panels_ms = float(timing.get("panels_ms", 0.0))
        panel_p95 = float(timing.get("panels_p95_ms", 0.0))
        lines = [
            f"FPS        {fps:5.1f}",
            f"Frame      {frame_time:5.1f} ms",
            f"World UI   {world_ms:5.2f} ms",
            f"Panels     {panels_ms:5.2f} ms",
            f"Panel p95  {panel_p95:5.2f} ms",
            f"Sprites    {sprite_count}",
            f"Combat     {combat_count}",
            f"Entities   {entity_count}",
            f"Collision  {collision_count}",
            f"Cache      {entries}",
            f"Text Hit   {cache_hit_rate:5.1f}%",
            f"Hit Stop   {hit_stop:.3f}",
            f"Spawn CD   {spawn_cooldown:.3f}",
        ]
        surface = self.renderer.display_surface
        compact = surface.get_width() < 1100 or surface.get_height() < 800
        if compact:
            lines = [
                lines[0],
                lines[1],
                f"UI total  {world_ms + panels_ms:5.2f} ms",
                f"F10 view  {self.compact_panel_focus().upper()}",
            ]

        if compact:
            primary_ui_ms = world_ms + panels_ms
            secondary_ui_ms = panel_p95
        else:
            primary_ui_ms = world_ms
            secondary_ui_ms = panels_ms
        panel_w = self.renderer.get_panel_width(lines)
        override = self.renderer.interaction.position_for(PANEL_PERFORMANCE)
        if layout is not None and override is None:
            panel_w, panel_h = self.renderer.measure_panel(
                lines, title="PERFORMANCE", reserve_close=True
            )
            panel_x, panel_y = layout.place_top_right(panel_w, panel_h)
        elif layout is not None:
            panel_x, panel_y = 10, 10
        else:
            panel_x = self.renderer.display_surface.get_width() - panel_w - 12
            panel_y = 12

        line_colors = {
            0: fps_color,
            1: frame_color,
            2: TEXT_OK
            if primary_ui_ms <= 4.0
            else TEXT_WARN
            if primary_ui_ms <= 8.0
            else TEXT_CRIT,
        }
        if not compact:
            line_colors[3] = (
                TEXT_OK
                if secondary_ui_ms <= 4.0
                else TEXT_WARN
                if secondary_ui_ms <= 8.0
                else TEXT_CRIT
            )
        self.renderer.draw_panel(
            panel_x,
            panel_y,
            lines,
            title="PERFORMANCE",
            line_colors=line_colors,
            panel_id=PANEL_PERFORMANCE,
            layout=layout if override is not None else None,
        )

    def handle_panel_event(self, event: pygame.event.Event) -> bool:
        """Route a mouse event to the debug panels; ``True`` if consumed.

        Called by the gameplay scene before the game logic sees the event, so
        a click on a panel never leaks into gameplay.
        """
        return self.renderer.interaction.handle_event(event)

    def reset_debug_panels(self) -> None:
        """Reopen every closed panel and forget drags and drops (F5)."""
        self.renderer.interaction.reset()

    def draw_debug_overlays(
        self,
        all_sprites: pygame.sprite.Group,
        camera: Camera,
        delta_time: float | None = None,
    ) -> None:
        self.world_ui.draw_debug_overlays(all_sprites, camera, delta_time)

    def draw_health_bars(
        self,
        entities: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        screen_rects: dict[int, pygame.Rect] | None = None,
    ) -> list[pygame.Rect]:
        """Draw the HP bars; return the rects they occupy.

        The caller merges them into the frame's presentation set, otherwise a
        bar drawn outside its sprite's dirty rect never reaches the screen.
        """
        return self.world_ui.draw_health_bars(entities, camera, screen_rects)

    def draw_hud(self, player: Any) -> list[pygame.Rect]:
        """Always-on player gauges: health, guard posture, dash, combo (UI-7).

        Returns the dirty rects the gauges occupy, for the caller to merge
        into the frame's presentation set.
        """
        return self.hud.draw(player)
