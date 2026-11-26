from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import pygame

from src.presentation.rendering.camera import Camera
from src.presentation.ui.hud import HUD
from src.presentation.ui.panel_renderer import PanelLayout, PanelRenderer, compact_panels
from src.presentation.ui.player_ui import PlayerUI
from src.presentation.ui.styles import TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN
from src.presentation.ui.world_overlay.metrics import COMBAT_PANEL_TITLE
from src.presentation.ui.world_ui import WorldUI
from src.simulation.level.scene_host import SceneHost

#: Stable ids of the interactive debug panels. They name the ``×``/drag state
#: kept by :class:`~src.presentation.ui.panel_renderer.PanelInteraction`, so a panel keeps
#: its closed flag and dropped position even when it moves in the draw order.
PANEL_PERFORMANCE = "performance"
PANEL_COMBAT = "combat"
PANEL_STATE = "state"
PANEL_STATS = "stats"
PANEL_SCENE = "scene"
PANEL_KEYS = "keys"
PANEL_LEGEND = "legend"


def _help_bench(layer_rows: list[str], compact: bool) -> list[str]:
    """The static key rows, after the live layer states have been filled in."""
    if compact:
        return [
            "1-0 attacks · V/B shots · G/P/T spawn",
            *layer_rows,
            "F6 freeze · F7 step · F8 replay · F9 export",
        ]
    return [
        "1-8 showcase · 9-0 air kit (in the air)",
        "V/B shots · C dummy · G/P/T spawn",
        *layer_rows,
        "F6 freeze · F7 step · F8 replay · F9 export",
        "× close · drag",
    ]


def _legend_rows(compact: bool) -> list[tuple[str, tuple[int, int, int] | None]]:
    """One table for both the legend text and its colours.

    The two used to be built separately, with the colour indices maintained by
    hand: a row inserted in one list silently recoloured the wrong line in the
    other. Deriving both from the same ordered rows makes that drift impossible.
    """
    from src.presentation.ui.world_overlay.metrics import PHASE_OUTLINE_COLORS
    from src.shared.colors import Colors

    if compact:
        return [
            ("green  hurtbox", Colors.debug_hurtbox),
            ("orange attack active", PHASE_OUTLINE_COLORS["active"]),
            ("gold   startup", PHASE_OUTLINE_COLORS["startup"]),
            ("cyan   broadphase", Colors.debug_broadphase),
            ("violet swept", Colors.debug_sweep),
            ("white  anchor", Colors.debug_anchor),
            ("purple juggle", Colors.debug_juggle),
        ]

    zone_colors = Colors.debug_hurtbox_zones
    return [
        ("blue/red  pushbox", None),
        ("green     hurtbox", None),
        ("thin      plain zone", zone_colors[0]),
        ("fill      xmult zone", zone_colors[1]),
        ("dashed    guarded zone", zone_colors[2]),
        ("orange    attack active", PHASE_OUTLINE_COLORS["active"]),
        ("gold      attack startup", PHASE_OUTLINE_COLORS["startup"]),
        ("grey      attack recovery", PHASE_OUTLINE_COLORS["recovery"]),
        ("cyan dot  broadphase", Colors.debug_broadphase),
        ("violet    swept shape", Colors.debug_sweep),
        ("white +   anchor", Colors.debug_anchor),
        ("P2/UBL    hit priority", None),
        ("purple    juggle gravity", Colors.debug_juggle),
    ]


class UIManager:
    """Facade pattern for the user interface."""

    def __init__(
        self,
        surface: pygame.Surface,
        density: float = 1.0,
        panel_scale: float = 1.0,
    ) -> None:
        #: ``density`` is the render target's pixel density, read off the camera
        #: by the renderer. It is a constructor argument rather than something
        #: set later because the first frame is drawn with it: a panel built at
        #: the design size and scaled on the next window change is a frame of
        #: unreadable text, and the first frame is the one the developer is
        #: looking at.
        #:
        #: ``panel_scale`` is here for the same reason and for one more. The
        #: overlay is built *lazily* -- on the first frame that needs it -- which
        #: is long after the settings file has been read. So a preference applied
        #: only from ``apply_settings`` reaches an overlay that does not exist
        #: yet, and the panels come up at the default however the file is
        #: written: the variable right, the drawing wrong. Passing it here means
        #: the object is correct the moment it exists.
        self.renderer = PanelRenderer(surface, density=density, panel_scale=panel_scale)
        self.player_ui = PlayerUI(self.renderer)
        self.world_ui = WorldUI(self.renderer)
        self.hud = HUD(self.renderer)
        self._compact_panel_focus = PANEL_STATE

    #: The panels F10 steps through in the compact layout, in order.
    COMPACT_ORDER = (PANEL_COMBAT, PANEL_STATE, PANEL_STATS, PANEL_SCENE, PANEL_KEYS, PANEL_LEGEND)

    def cycle_compact_panel(self) -> str:
        order = self.COMPACT_ORDER
        for _ in order:
            self._compact_panel_focus = order[
                (order.index(self._compact_panel_focus) + 1) % len(order)
            ]
            if not self.renderer.interaction.is_closed(self._compact_panel_focus):
                break
        return self._compact_panel_focus

    def _panel_footers(self) -> dict[str, str]:
        """How to get around the panels, said on the panel being looked at.

        In the compact layout that is the one panel shown, with where it sits in
        the F10 cycle; with every panel shown it is said once, on PERFORMANCE.
        """
        if not compact_panels():
            return {PANEL_PERFORMANCE: "F11 one at a time"}
        focus = self._compact_panel_focus
        position = self.COMPACT_ORDER.index(focus) + 1
        return {focus: f"F10 next {position}/{len(self.COMPACT_ORDER)} · F11 all"}

    def compact_panel_focus(self) -> str:
        return self._compact_panel_focus

    def draw_compact_panel(
        self,
        player: Any,
        layout: PanelLayout,
        scene_host: SceneHost | None = None,
    ) -> int:
        panel_id = self._compact_panel_focus
        self.renderer.footers = self._panel_footers()
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

        This is the gate, rendered -- not a report of what the gate last decided:
        each button, high then low, resolved from the fighter's posture with
        nothing running, as :func:`resolve_move` would. A press with no move in
        this posture shows a dash.
        """
        from src.simulation.combat.frame_data import AttackButton
        from src.simulation.entities.attack_moves import MoveContext, resolve_move

        # Duck-typed off a real player: a player with no stance draws an empty
        # table instead of taking the frame down.
        stance: Any = getattr(player, "stance", None)
        cooldowns = getattr(getattr(player, "combat", None), "cooldowns", {}) or {}
        rows: list[tuple[str, tuple[int, int, int]]] = [
            (f"Stance  {getattr(stance, 'value', stance)}", TEXT_OK)
        ]
        # One row per button, high then low: four rows would not fit the
        # small displays the panel stack has to hold.
        for button, presses in (
            ("Slash", (AttackButton.SLASH_HIGH, AttackButton.SLASH_LOW)),
            ("Beat", (AttackButton.BEAT_HIGH, AttackButton.BEAT_LOW)),
        ):
            names = [
                resolve_move(press, MoveContext(stance)) if stance is not None else None
                for press in presses
            ]
            shown = " · ".join("—" if name is None else str(name) for name in names)
            cooling = [float(cooldowns.get(name, 0.0)) for name in names if name is not None]
            remaining = max(cooling, default=0.0)
            if remaining > 0.0:
                rows.append((f"{button:<6}{shown} {remaining:.1f}s", TEXT_WARN))
            else:
                rows.append((f"{button:<6}{shown}", TEXT_MUTED))
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

        def layer(key: str, name: str) -> str:
            if key not in states:
                return f"{name}"
            return f"{name} {'on' if states[key] else 'off'}"

        # Every key with its name, and every layer with its state: a row that
        # says "F1-F5 layers" leaves the reader to press each one to find out.
        layer_rows = [
            f"F1 {layer('boxes', 'boxes')} · F2 {layer('labels', 'labels')}"
            f" · F3 {layer('velocities', 'speed')}",
            f"F4 {layer('statics', 'statics')} · F5 {layer('panels', 'panels')}",
        ]
        bench = _help_bench(layer_rows, compact)

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
        rows = _legend_rows(compact)
        lines = [text for text, _ in rows]
        line_colors = {index: color for index, (_, color) in enumerate(rows) if color is not None}
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
            f"FPS        {fps:5.0f}",
            f"Frame      {frame_time:5.0f} ms",
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
            # FPS and frame time; the way around the panels is on the panel
            # being looked at, not here.
            lines = lines[:2]

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
        screen_rects: Mapping[int, pygame.Rect | pygame.FRect] | None = None,
    ) -> list[pygame.Rect]:
        """Draw the HP bars; return the rects they occupy.

        The caller merges them into the frame's presentation set, otherwise a
        bar drawn outside its sprite's rect is erased with everything else on
        the next frame, so there is nothing left to declare.
        """
        return self.world_ui.draw_health_bars(entities, camera, screen_rects)

    def draw_hud(self, player: Any) -> None:
        """Always-on player gauges: health and rally, blood, dash, combo (UI-7)."""
        self.hud.draw(player)

    @contextmanager
    def drawing_within(self, area: pygame.Rect | None) -> Iterator[None]:
        """Lay out and paint inside ``area`` of the target, not the whole of it.

        Under the *zoom* fit the window shows a crop of the target: anchored to
        the target's corners, the gauges are painted in the part that is cut
        off. Painting into a subsurface of the shown part puts every corner
        anchor on a corner the player sees, with no layout knowing about it.
        """
        surface = self.renderer.surface
        bounds = surface.get_rect()
        shown = bounds if area is None else area.clip(bounds)
        if shown == bounds or shown.width <= 0 or shown.height <= 0:
            yield
            return
        self.renderer.surface = surface.subsurface(shown)
        try:
            yield
        finally:
            self.renderer.surface = surface

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
        self.renderer.footers = self._panel_footers()
        layout = PanelLayout(
            self.renderer.surface.get_width(),
            # Above the HUD's gauges, which are drawn on every frame.
            self.renderer.surface.get_height() - self.hud.reserved_height(),
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
