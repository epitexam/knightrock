from collections.abc import Iterable
from typing import Any

import pygame

from src.core.level.scene_host import SceneHost
from src.core.rendering.camera import Camera
from src.ui.hud import HUD
from src.ui.panel_renderer import PanelLayout, PanelRenderer, compact_panels
from src.ui.player_ui import PlayerUI
from src.ui.styles import TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN
from src.ui.world_overlay_metrics import COMBAT_PANEL_TITLE
from src.ui.world_ui import WorldUI

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

    def __init__(self, surface: pygame.Surface, density: float = 1.0) -> None:
        #: ``density`` is the render target's pixel density, read off the camera
        #: by the renderer. It is a constructor argument rather than something
        #: set later because the first frame is drawn with it: a panel built at
        #: the design size and scaled on the next window change is a frame of
        #: unreadable text, and the first frame is the one the developer is
        #: looking at.
        self.renderer = PanelRenderer(surface, density=density)
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
        scene_host: SceneHost | None = None,
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
            return self.draw_scene_panel(10, 10, scene_host, layout, compact=True)
        if panel_id == PANEL_KEYS:
            return self.draw_help_panel(
                10, 10, layout, self.world_ui.layers, compact=True, player=player
            )
        return self.draw_legend_panel(10, 10, layout, compact=True)

    def set_surface(self, surface: pygame.Surface, density: float = 1.0) -> None:
        """Adopt a new render target, at the density it implies.

        ``world_ui`` reads its surface from the panel renderer, so there is
        nothing to reassign here; the density is what the *sizes* need, and it
        is read off the camera by the renderer rather than measured twice.
        """
        self.renderer.set_surface(surface, density)

    def set_ui_scale(self, scale: float) -> None:
        self.hud.set_scale(scale)

    def set_panel_scale(self, scale: float) -> None:
        """Hand the player's debug-panel scale to the renderer that draws them.

        Distinct from :meth:`set_ui_scale`, which is the HUD and the menus and
        leaves the debug panels alone: an interface-scale preference of 0.8 has
        never moved a panel, and folding the two together would make one setting
        silently control the other's subject.
        """
        self.renderer.set_panel_scale(scale)

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
        scene_host: SceneHost | None,
        layout: PanelLayout | None = None,
        compact: bool = False,
    ) -> int:
        """Show active scene, current level, deaths and live entity counts.

        Takes a :class:`SceneHost` rather than the application: the panel needs
        to know which scene is on top and nothing else, and `Any` said nothing
        even about that. A `None` host draws the panel with "None" for the
        scene, which is what a level rendered outside the scene stack is.
        """
        if self.renderer.interaction.is_closed(PANEL_SCENE):
            return 0
        current = None if scene_host is None else scene_host.scene_manager.current
        scene_name = type(current).__name__ if current else "None"

        level_id = getattr(current, "level_id", None)
        deaths = getattr(current, "level", None)
        deaths_n = deaths.deaths if deaths is not None else 0
        level_str = str(level_id) if level_id is not None else "-"

        surface = self.renderer.surface
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

    @staticmethod
    def _attack_button_rows(player: Any) -> list[tuple[str, tuple[int, int, int]]]:
        """What each attack button would throw from where the fighter is standing.

        This is the gate, rendered -- not a report of what the gate last decided.
        ``start_attack`` tests posture before cooldown, and both are readable from
        ``player.stance``, ``BUTTON_MOVES`` and ``combat.cooldowns``, so the
        reason for a refusal is visible *before* the press rather than logged
        after it. Nothing has to publish a refusal for that: ``refusal.py`` notes
        no consumer exists yet, and the obvious one is a log, when the cheaper
        answer is to show the rule.

        The rows come from iterating ``BUTTON_MOVES``, never from a list written
        out here. A button added to the table appears without a UI edit -- the
        property whose absence let ``air_rise`` drift to a guard height its
        grounded counterpart did not have.

        A button with no move in this posture shows a dash. Printing the standing
        move instead would claim it works from here, which is the one thing it
        must not say.
        """
        from src.core.input.input_actions import InputAction
        from src.entities.attack_moves import BUTTON_MOVES, move_for_button

        # Read the way the rest of this panel reads: duck-typed off a real player.
        # A player with no stance resolves every button to ``None`` rather than
        # raising, which is the right failure for a debug overlay -- it draws an
        # empty table instead of taking the frame down.
        stance: Any = getattr(player, "stance", None)
        cooldowns = getattr(getattr(player, "combat", None), "cooldowns", {}) or {}
        rows: list[tuple[str, tuple[int, int, int]]] = [
            (f"Stance  {getattr(stance, 'value', stance)}", TEXT_OK)
        ]
        for action in BUTTON_MOVES:
            # The action, not the key it defaults to. ``SPECIAL_ATTACK`` has no
            # keyboard binding at all and the rest are rebindable, so printing a
            # letter would be a claim this panel cannot keep -- the same mistake
            # as a guard height a move's grounded twin did not have.
            label = "special" if action is InputAction.SPECIAL_ATTACK else action.value
            name = move_for_button(action, stance)
            if name is None:
                text, color = f"{label:<7} —", TEXT_MUTED
            else:
                remaining = float(cooldowns.get(name, 0.0))
                if remaining > 0.0:
                    text, color = f"{label:<7} {name} {remaining:.1f}s", TEXT_WARN
                else:
                    text, color = f"{label:<7} {name}", TEXT_MUTED
            rows.append((text, color))
        return rows

    def draw_help_panel(
        self,
        x: int,
        y: int,
        layout: PanelLayout | None = None,
        layers: dict[str, bool] | None = None,
        compact: bool = False,
        player: Any = None,
    ) -> int:
        """The attack buttons from where the fighter stands, plus the bench keys.

        The live block comes first because it is what a developer is reading while
        playing; the static key list is reference and is the same every frame.

        ``1-0`` rather than ``1-6``: the air keys only fire off the ground, so the
        two halves of that range behave differently and saying so is what keeps a
        developer from reading a refused press as a dead key.
        """
        if self.renderer.interaction.is_closed(PANEL_KEYS):
            return 0
        states = layers or {}

        def mark(key: str) -> str:
            if key not in states:
                return ""
            return " [ON]" if states[key] else " [OFF]"

        # The bench list is reference, identical every frame, and it was fifteen rows for
        # a sentence's worth of facts -- F1 through F5 one per line, which is five
        # rows to say there are five toggles. Merging it is what keeps the panel
        # placeable at 640x480: the live block adds six rows, and this panel is the
        # tallest in the stack, so every bench row it did not need was a row the
        # column flow could not find a slot for.
        # One range for the whole top row rather than ``1-6`` and ``7-0``: the
        # split reads as two ranges, and a reader checking whether their key is
        # listed has to work out which half it is in. The distinction that matters
        # is in the note beside it, not in the range itself.
        # ``1-6`` and ``7-0`` rather than one ``1-0``: two explicit ranges, because a
        # range written high-to-low is a thing a reader has to work out, and
        # "which half of the row is my key in" is not a question a legend should
        # raise. Splitting it is also what let the legend drop the air half when
        # the air kit landed -- one range would have covered it by accident.
        bench = [
            "1-6 showcase · 7-0 air kit (in the air)",
            "V/B shots · C dummy · G/P/T spawn",
            f"F1-F5 layers{mark('boxes')}",
            "F6-F9 sim · F10 next · F11 layout",
            "× close · drag",
        ]
        if compact:
            bench = [
                "1-0 attacks · V/B shots · G/P/T spawn",
                "F1-F5 layers · F6-F11 tools · × close",
            ]

        lines: list[str] = []
        line_colors: dict[int, tuple[int, int, int]] = {}
        if player is not None:
            rows = self._attack_button_rows(player)
            lines.extend(text for text, _ in rows)
            line_colors.update({index: color for index, (_, color) in enumerate(rows)})
        lines.extend(bench)
        return self.renderer.draw_panel(
            x,
            y,
            lines,
            title="DEBUG KEYS",
            layout=layout,
            panel_id=PANEL_KEYS,
            line_colors=line_colors or None,
        )

    def draw_legend_panel(
        self, x: int, y: int, layout: PanelLayout | None = None, compact: bool = False
    ) -> int:
        """Persistent color legend for the world-space combat overlay."""
        if self.renderer.interaction.is_closed(PANEL_LEGEND):
            return 0
        from src.core.colors import Colors
        from src.ui.world_overlay_metrics import PHASE_OUTLINE_COLORS

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

        The lines are collected by ``world_ui.panels.draw_metrics_panel`` (a
        no-op when ``DEBUG`` is off); drawing them through the column flow
        keeps them under the side panels instead of a fixed spot that other
        panels could stack on.
        """
        if self.renderer.interaction.is_closed(PANEL_COMBAT):
            return 0
        content = self.world_ui.panels.combat_panel()
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
            f"Overlays   {world_ms:5.2f} ms",
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
        if compact_panels():
            lines = [
                lines[0],
                lines[1],
                f"F10 view  {self.compact_panel_focus().upper()}",
            ]

        if compact_panels():
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
            panel_x = self.renderer.surface.get_width() - panel_w - 12
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
        if not compact_panels():
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
        all_sprites: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        delta_time: float | None = None,
    ) -> None:
        """Overlay the world-space debug layer.

        Takes any iterable rather than a group: the draw planes are separate
        groups, and the overlay wants all of them.
        """
        self.world_ui.draw_debug_overlays(all_sprites, camera, delta_time)

    def draw_health_bars(
        self,
        entities: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        screen_rects: dict[int, pygame.Rect] | None = None,
    ) -> list[pygame.Rect]:
        """Draw the HP bars; return the rects they occupy.

        The caller merges them into the frame's presentation set, otherwise a
        bar drawn outside its sprite's rect is erased with everything else on
        the next frame, so there is nothing left to declare.
        """
        return self.world_ui.draw_health_bars(entities, camera, screen_rects)

    def draw_hud(self, player: Any) -> None:
        """Always-on player gauges: health, guard posture, dash, combo (UI-7)."""
        self.hud.draw(player)

    # -- the WorldOverlay port -------------------------------------------------
    #
    # `core/rendering/overlay.py` declares what the renderer needs; these are
    # the implementations. The panel layout moved across with them because the
    # renderer used to own it, and a port that stopped one call short would have
    # left `PanelLayout` imported in `core` -- the very dependency the port
    # exists to remove.

    def draw_debug_panels(
        self,
        *,
        player: Any = None,
        scene_host: SceneHost | None = None,
        debug_stats: dict[str, float] | None = None,
        **counters: Any,
    ) -> None:
        """Draw the screen-side debug panels from the renderer's counters.

        PERFORMANCE is pinned first so the column flow can reserve it and wrap
        around it; COMBAT counters then lead the flow, so the tall PLAYER
        STATE / STATS panels can never overdraw them.
        """
        self.renderer.interaction.begin_frame()
        if not self.world_ui.layers.get("panels", True):
            return
        layout = PanelLayout(
            self.renderer.surface.get_width(),
            self.renderer.surface.get_height(),
            scale=self.renderer.screen_scale,
        )
        self.draw_performance_panel(
            layout=layout,
            debug_stats=debug_stats or {},
            **counters,
        )
        if compact_panels():
            self.draw_compact_panel(player, layout, scene_host)
            return
        self.draw_combat_panel(layout)
        self.draw_state_panel(10, 10, player, layout=layout)
        self.draw_stats_panel(10, 10, player, layout=layout)
        if scene_host is not None:
            self.draw_scene_panel(10, 10, scene_host, layout=layout)
        self.draw_help_panel(10, 10, layout=layout, layers=self.world_ui.layers, player=player)
        self.draw_legend_panel(10, 10, layout=layout)

    def draw_metrics_panel(self, player: Any, hit_stop: float) -> None:
        """The always-on combat metrics readout."""
        self.world_ui.panels.draw_metrics_panel(player=player, hit_stop=hit_stop)

    def note_clash(self, clash: Any) -> None:
        """Record a clash so the overlay can mark it where it happened."""
        self.world_ui.panels.note_clash(clash)

    def stamp_clash_marker(self, camera: Camera) -> None:
        """Draw the clash marker again, over the debug panels."""
        self.world_ui.panels.stamp_clash_marker(camera)

    def update_metrics(self, metrics: Any) -> None:
        """Feed the contact pipeline's per-tick counters to the overlay."""
        self.world_ui.panels.update_metrics(metrics)
