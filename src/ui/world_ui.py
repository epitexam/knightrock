"""World-space UI overlays for entities and combat debugging.

UX rules (debug readability pass):
- Viewport culling: off-screen sprites draw nothing, not even labels.
- Color by faction: blue hitbox = player, red = foe, grey = neutral. Hurtboxes
  stay green, offensive boxes orange, projectiles draw their flight vector.
- Label cards: each datum gets its own row (header, HP, attack, flags), each
  token its own color — name by faction, HP by ratio, attack name in gold,
  every flag in its semantic color. Rows never collapse into one running
  sentence; static geometry (hazards, platforms, exits) gets an outline
  only — no text.
- Vertical stack (debug): entity, then its health bar, then one attack header
  chip per attacker (gold name + phase:frame + badges, timeline bar tucked
  underneath, leader line to the first attack box), then its label card —
  each tier reserves room for the tiers painted below it, so no tier covers
  another. Near the top of the screen the bar flips below the entity, the
  header follows it, and the card takes the freed space above.
- Attack box indices ride their own box (a haloed solid/hollow dot in the
  box corner) instead of floating in the tier stack: one header chip per
  attacker, no constellation of pills.
- Hurtbox zones read by shape, never by text: empty zones keep the legacy
  thin green outline; boosted zones (mult != 1.0) add a translucent fill + a
  thicker outline in the zone color; guarded zones (tags) draw a dashed seal.
  Names, mults and tags live on the label card's ``ZONE`` row, never in the
  world — zero glyphs to overlap, whatever the zone count.
- Velocity vectors are arrows, not hairlines: a tapered shaft, a filled
  triangular head, a pivot dot on the entity and a dark rim so the silhouette
  survives a bright sky. The head length is clamped, and a minimum drawn
  length keeps slow vectors readable.
- A velocity vector is painted red while the typed hit cause is fresh **or**
  while the knockback state still carries the entity (a launch outlives the
  freshness window), gold on a parry, yellow for locomotion.
- Labels never stack: each label dodges upward (then below its entity) to a
  free slot, and is dropped rather than overdrawn when no slot is left.
- Health bars and attack annotations are placement obstacles too: the
  placer keeps label cards clear of everything drawn between the entity
  and its card, so neither a bar nor a timeline can end up painted over a
  card drawn the same frame — and annotation text dodges the bar painted
  after it. Every world-space annotation clamps back inside the display
  instead of clipping at the screen edge.
- The COMBAT counter panel joins the screen-space debug column flow — it
  leads it, right under the pinned PERFORMANCE gauge — instead of blitting
  at a fixed spot where side panels could overdraw it; it stays gated
  behind ``Debug``.
- Layers are toggleable at runtime (F1 boxes, F2 labels, F3 velocities,
  F4 statics) via :meth:`WorldUI.toggle`, wired in ``GameplayScene``.

Where the numbers live
----------------------
Every dimension is in :mod:`src.ui.world_overlay_metrics`, in world units,
and is multiplied by the pixel density exactly once, by
``WorldOverlayMetrics``. They used to be module constants here, interleaved
with the drawing, which is the worst of both: a constant that only matters to
the label placer is invisible when you are looking at the box drawer, and the
drawing is buried under four hundred lines of tables no reader of it needs.

What is still in this file
-------------------------
The debug drawing, in five parts that are being moved out one at a time:
label cards, debug boxes, velocity arrows, the screen-space panels, and --
already gone -- the health bars and the dimensions.

The health bars went first and on their own argument rather than their size:
``Level.draw`` calls them *before* it checks ``DEBUG``, so they are painted
on every frame of a real game while everything else here is behind ``F1``.
A production path inside a debug module is the arrangement that decays
quietly, because it gets reviewed with the debug layer's eye and its tests
get counted against the debug layer's coverage. See
:mod:`src.ui.world_overlay_bars`.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import pygame
import pygame.gfxdraw
from pygame.math import Vector2

from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.core.settings import Debug
from src.entities.components.reaction import ReactionStatus
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER, TEXT_CRIT, TEXT_MUTED, TEXT_WARN
from src.ui.world_overlay_bars import (
    draw_health_bars as _draw_health_bars,
)
from src.ui.world_overlay_bars import (
    has_health_bar as _has_health_bar,
)
from src.ui.world_overlay_bars import (
    health_bar_rect as _health_bar_rect,
)
from src.ui.world_overlay_bars import (
    health_colour as _health_colour,
)
from src.ui.world_overlay_geo import GeoLayer
from src.ui.world_overlay_metrics import (  # noqa: F401 - re-exported
    ANNOTATION_CHIP_FILL,
    ANNOTATION_CHIP_PAD,
    ANNOTATION_MAX_DODGES,
    ANNOTATION_TIER_GAP,
    ATTACK_HEADER_RULE_GAP,
    ATTACK_HEADER_TEXT_GAP,
    BOX_DOT_CORE_RADIUS,
    BOX_DOT_INSET,
    BOX_DOT_RADIUS,
    BOX_DOT_RIM,
    BOX_DOT_RIM_WIDTH,
    CLASH_MARKER_LIFETIME,
    CLASH_MARKER_RADIUS,
    CLASH_TICK_S,
    COMBAT_PANEL_TITLE,
    CULL_MARGIN_PX,
    HEALTH_BAR_ANCHOR_GAP,
    HEALTH_BAR_HEIGHT,
    HEALTH_BAR_LABEL_GAP,
    HIT_HEIGHT_BADGES,
    LABEL_ANCHOR_GAP,
    LABEL_BAR_CLEARANCE,
    LABEL_DIVIDER_BOTTOM,
    LABEL_DIVIDER_TOP,
    LABEL_LINE_GAP,
    LABEL_MAX_NUDGES,
    LABEL_NUDGE_PX,
    LABEL_PAD_X,
    LABEL_PAD_Y,
    LABEL_SEP,
    LABEL_TAG,
    METRICS_TICK_DIVISOR,
    OVERLAY_LAYERS,
    PHASE_OUTLINE_COLORS,
    SWEEP_ARROW_HEAD,
    SWEEP_DISPLAY_MIN_PX,
    SWEEP_GHOST_WIDTH,
    TIMELINE_BAR_HEIGHT,
    TIMELINE_MAX_WIDTH,
    TIMELINE_PX_PER_FRAME,
    VELOCITY_HEAD_MAX,
    VELOCITY_HEAD_MIN,
    VELOCITY_HEAD_RATIO,
    VELOCITY_HEAD_WIDTH_CAP,
    VELOCITY_HEAD_WIDTH_RATIO,
    VELOCITY_MIN_LENGTH,
    VELOCITY_MIN_SPEED,
    VELOCITY_NECK_WIDTH,
    VELOCITY_OUTLINE,
    VELOCITY_OUTLINE_WIDTH,
    VELOCITY_PREVIEW_S,
    VELOCITY_TAIL_RADIUS,
    VELOCITY_TAIL_WIDTH,
    ZONE_BOOST_OUTLINE_WIDTH,
    ZONE_FILL_ALPHA,
    ZONE_OUTLINE_WIDTH,
    ZONE_SEAL_DASH,
    ZONE_SEAL_GAP,
    ZONE_SEAL_WIDTH,
    WorldOverlayMetrics,
)
from src.ui.world_overlay_metrics import (
    scaled_world_px as _scaled,
)
from src.ui.world_overlay_shared import (
    AnnotationSink,
    debug_reference,
    display_name,
    faction,
    label_color,
)

if TYPE_CHECKING:
    pass


#: One label row: ``(text, color)`` tokens laid out left to right.
_Segments = list[list[tuple[str, Color]]]

#: A collected label: sort key, colored rows, faction accent, screen
#: anchor, clearance above (bar above the entity) and below (bar flipped
#: under the entity near the top of the screen), and the sprite itself so
#: the placer can treat its health bar as an obstacle.
_LabelRequest = tuple[
    tuple[int, float, float], _Segments, Color, pygame.FRect, int, int, pygame.sprite.Sprite
]


def arrow_outline(
    start: Vector2,
    direction: Vector2,
    length: float,
    head_length: float,
    head_half_width: float,
) -> list[tuple[int, int]]:
    """Silhouette of a velocity arrow: a tapered shaft plus a triangular head.

    One single seven-point polygon (tail, neck, barb, tip, barb, neck, tail)
    so the shaft and the head can never leave a seam. ``direction`` must be a
    unit vector, ``start`` the screen-space pivot and ``length`` the drawn
    length (already floored to ``VELOCITY_MIN_LENGTH``).
    """
    normal = Vector2(-direction.y, direction.x)
    tip = start + direction * length
    neck = tip - direction * head_length
    corners = (
        start + normal * (VELOCITY_TAIL_WIDTH / 2.0),
        neck + normal * (VELOCITY_NECK_WIDTH / 2.0),
        neck + normal * head_half_width,
        tip,
        neck - normal * head_half_width,
        neck - normal * (VELOCITY_NECK_WIDTH / 2.0),
        start - normal * (VELOCITY_TAIL_WIDTH / 2.0),
    )
    return [(round(corner.x), round(corner.y)) for corner in corners]


def join_flag_tokens(flags: list[tuple[str, Color]]) -> list[tuple[str, Color]]:
    """Interleave flag tokens with a bright ``|`` separator."""
    joined: list[tuple[str, Color]] = [flags[0]]
    for text, color in flags[1:]:
        joined.append((" | ", LABEL_SEP))
        joined.append((text, color))
    return joined


class WorldUI:
    """Render health bars and optional world-space diagnostics.

    Every dimension here is written in **world units** and multiplied by the
    target's pixel density at paint time, through :meth:`px` and :meth:`stroke`.
    That distinction is the whole reason this layer is legible: the rectangles
    come from ``camera.apply``, which scales, while the *widths*, *paddings* and
    *gaps* used to be handed to pygame raw -- so on a window where the world is
    drawn 1.9x larger, a 1px hitbox outline landed at 53% of its weight and the
    overlay read as "F1 does nothing". A tool that cannot be seen is a tool
    that is broken.
    """

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer
        # ``statics`` starts off: a level carries ~840 terrain tiles whose
        # outline tells you nothing, and drawing them is the single most
        # expensive thing the overlay does. Measured on level 0 at 1280x720
        # with DEBUG=1, the whole overlay pass goes from 1.98 ms to 0.09 ms
        # when the layer is off -- 1.9 ms of a 16.7 ms budget for a picture
        # of the tileset. F4 brings the layer back.
        self.layers: dict[str, bool] = {name: name != "statics" for name in OVERLAY_LAYERS}
        self.metrics_text: tuple[str, ...] = ()
        self._metrics_whiffs = 0
        #: Colored ``(text, color)`` lines of the unified COMBAT panel,
        #: refreshed by :meth:`draw_metrics_panel`, drawn by the debug flow.
        self.combat_panel_lines: list[tuple[str, Color]] = []
        self._metrics_tick = 0
        self.clash_point: tuple[float, float] | None = None
        self._clash_ttl: float = 0.0
        #: Health-bar rects seen on the previous overlay frame: labels dodge
        #: them too, since bars paint after cards but belong to the same
        #: frame's stack (entity -> bar -> card).
        self._previous_bar_obstacles: list[pygame.Rect] = []
        #: Attack annotation rects drawn this frame, keyed by sprite id. The
        #: box pass writes them, the card pass reads them, and the sink is what
        #: makes that one-way; see ``world_overlay_shared.AnnotationSink``.
        self._sink = AnnotationSink()
        self._metrics_scale: float = -1.0
        self._metrics = WorldOverlayMetrics(1.0)
        #: Producer half of the frame: the sprite geometry and the tiers drawn
        #: above it. Built once, and reads the surface and the metrics live so a
        #: resize needs no push.
        self._geo = GeoLayer(self.renderer, lambda: self.metrics, self._sink)

    @property
    def annotation_rects(self) -> dict[int, list[pygame.Rect]]:
        """This frame's annotations, keyed by sprite id."""
        return self._sink.rects

    @property
    def annotation_obstacles(self) -> list[pygame.Rect]:
        """This frame's annotation rects, flattened, in draw order."""
        return self._sink.obstacles

    @property
    def metrics(self) -> WorldOverlayMetrics:
        """The overlay dimensions for the current density, rebuilt when it moves.

        Cached on the scale, so a static window costs one identity comparison per
        frame and a resize costs one table.
        """
        scale = self.renderer.world_scale
        if scale != self._metrics_scale:
            self._metrics_scale = scale
            self._metrics = WorldOverlayMetrics(scale)
        return self._metrics

    def stroke(self, world_px: int = 1) -> int:
        """An outline of ``world_px`` art pixels, in whole target pixels.

        Floored at 1, so a density below one thins the overlay rather than
        deleting it: *not drawing the outline* is the one outcome a debug tool
        must never produce.
        """
        return _scaled(world_px, self.renderer.world_scale)

    def toggle(self, layer: str) -> bool:
        """Flip an overlay layer, returning its new state."""
        if layer not in self.layers:
            raise KeyError(f"Unknown overlay layer: {layer!r}")
        self.layers[layer] = not self.layers[layer]
        return self.layers[layer]

    def draw_debug_overlays(
        self,
        all_sprites: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        delta_time: float | None = None,
    ) -> None:
        # Fresh annotation bookkeeping: the rects drawn this frame feed both
        # the card obstacles and the card clearances.
        self._sink.clear()
        if not any(self.layers[name] for name in ("boxes", "labels", "velocities", "statics")):
            return
        screen_width = self.surface.get_width()

        # Labels are collected first and drawn after the loop so they can
        # dodge each other instead of stacking on shared screen space.
        requests: list[_LabelRequest] = []
        for sprite in all_sprites:
            # Terrain tiles are ~840 of a level's sprites and have no hitbox,
            # no combat state and no velocity, so `is_static` below is the
            # gate that keeps the overlay cheap: `_debug_reference` builds one
            # to three FRects per call, and the `statics` toggle skips all of
            # it for them.
            #
            # There used to be an exact-type test above this one, skipped on
            # the theory that it would catch the tiles for free. It never
            # matched anything: the tiles are `src.core.sprites.Sprite`, a
            # *subclass* of `pygame.sprite.Sprite`, so `type(sprite) is
            # pygame.sprite.Sprite` was false for every one of them and each
            # tile paid for a check that bought nothing. `is_static` is the
            # real test and it is the one below.
            is_static = getattr(sprite, "hitbox", None) is None
            if is_static and not self.layers["statics"]:
                continue
            reference = debug_reference(sprite)
            if reference is None or not camera.is_visible(reference):
                continue  # culled: off-screen, not worth a single pixel
            if self.layers["boxes"]:
                self._geo.draw_boxes(sprite, camera)
            if self.layers["velocities"]:
                self._geo.draw_velocity(sprite, camera)
            request = self._label_request(sprite, reference, is_static, camera)
            if request is not None:
                requests.append(request)

        if requests:
            requests.sort(key=lambda request: request[0])
            self._draw_labels(requests, screen_width, self.surface.get_height())

        self._draw_clash_marker(camera, delta_time)

    def _label_request(
        self,
        sprite: pygame.sprite.Sprite,
        reference: pygame.FRect,
        is_static: bool,
        camera: Camera,
    ) -> _LabelRequest | None:
        if not self.layers["labels"] or is_static:
            return None
        segments = self._label_segments(sprite)
        if segments is None:
            return None
        anchor = camera.apply(reference)
        priority = self._label_priority(sprite, anchor)
        above_lift, below_drop = self._label_clearances(sprite, anchor)
        return (
            priority,
            segments,
            label_color(sprite),
            anchor,
            above_lift,
            below_drop,
            sprite,
        )

    @property
    def surface(self) -> pygame.Surface:
        """The surface this overlay draws into.

        Derived rather than copied at construction. It used to be assigned once,
        and every path that replaced the render target had to remember to
        reassign it -- one that forgot would have the overlay drawing into an
        orphaned surface while the rest of the frame went to the new one, with
        no symptom until the two sizes differ.
        """
        return self.renderer.surface

    def update_metrics(self, metrics: object) -> None:
        self._metrics_tick += 1
        if self._metrics_tick % METRICS_TICK_DIVISOR:
            return
        pairs = int(getattr(metrics, "pairs_tested", 0) or 0)
        overlaps = int(getattr(metrics, "overlaps", 0) or 0)
        contacts = int(getattr(metrics, "contacts", 0) or 0)
        self._metrics_whiffs = max(0, pairs - overlaps)
        self.metrics_text = (
            f"pairs {pairs}",
            f"overlaps {overlaps}",
            f"contacts {contacts}",
        )

    def note_clash(self, point: tuple[float, float] | None) -> None:
        """Record a fresh clash point (world px) to flash in the world."""
        if point is not None:
            self.clash_point = point
            self._clash_ttl = CLASH_MARKER_LIFETIME

    def draw_metrics_panel(
        self,
        metrics: object | None = None,
        player: object | None = None,
        hit_stop: float | None = None,
    ) -> None:
        """Refresh the cached COMBAT lines (drawn later by the debug flow).

        The counters are cached once per metrics tick into
        ``combat_panel_lines`` and blitted with the other screen panels by
        :meth:`UIManager.draw_combat_panel`, so side panels can never stack
        over them. Debug-only: nothing is collected when ``DEBUG`` is off.
        """
        if not Debug.is_enabled():
            return
        if metrics is not None:
            self.update_metrics(metrics)
        if not self.metrics_text:
            return
        lines: list[tuple[str, Color]] = [
            *((line, Colors.off_white) for line in self.metrics_text),
            (f"whiffs {self._metrics_whiffs}", TEXT_MUTED),
        ]
        attack = self._geo.live_attack_text(player)
        if attack is not None:
            lines.append((f"atk {attack}", Colors.gold))
        if hit_stop:
            lines.append((f"hit-stop {hit_stop:.2f}s", TEXT_WARN))
        if self._clash_ttl > 0.0:
            lines.append(("CLASH", TEXT_CRIT))
        self.combat_panel_lines = lines

    def combat_panel(self) -> tuple[str, list[tuple[str, Color]]] | None:
        """``(title, lines)`` for the debug panel flow, or ``None`` when empty."""
        if not self.combat_panel_lines:
            return None
        return (COMBAT_PANEL_TITLE, self.combat_panel_lines)

    def _draw_clash_marker(self, camera: Camera, delta_time: float | None = None) -> None:
        """Expanding ring at the last clash point; fades over its lifetime."""
        if self._clash_ttl <= 0.0 or self.clash_point is None:
            return
        self._clash_ttl -= CLASH_TICK_S if delta_time is None else max(0.0, delta_time)
        self._paint_clash_ring(camera)

    def stamp_clash_marker(self, camera: Camera) -> None:
        """Repaint the clash ring after the health bars, without decaying it.

        The health bars paint after the debug overlays; this second stamp
        lands on top of them so a clash ring is never hidden behind a bar.
        """
        if self._clash_ttl <= 0.0 or self.clash_point is None:
            return
        self._paint_clash_ring(camera)

    def _paint_clash_ring(self, camera: Camera) -> None:
        point = self.clash_point
        if point is None:
            return
        anchor = camera.apply(pygame.FRect(point[0] - 1, point[1] - 1, 2, 2))
        center = (round(anchor.centerx), round(anchor.centery))
        progress = 1.0 - self._clash_ttl / CLASH_MARKER_LIFETIME
        radius = round(self.metrics.clash_radius * (0.5 + progress))
        pygame.draw.circle(self.surface, Colors.gold, center, radius, width=2)
        arm = 5
        pygame.draw.line(
            self.surface,
            Colors.white,
            (center[0] - arm, center[1] - arm),
            (center[0] + arm, center[1] + arm),
            width=1,
        )
        pygame.draw.line(
            self.surface,
            Colors.white,
            (center[0] - arm, center[1] + arm),
            (center[0] + arm, center[1] - arm),
            width=1,
        )

    def _label_lines(self, sprite: pygame.sprite.Sprite) -> list[str] | None:
        segments = self._label_segments(sprite)
        if segments is None:
            return None
        return [" ".join(text.strip() for text, _ in line) for line in segments]

    def _label_segments(self, sprite: pygame.sprite.Sprite) -> _Segments | None:
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            return self._entity_segments(sprite, state_machine)
        if getattr(sprite, "hitbox", None) is not None:
            return [[(self._projectile_line(sprite), Colors.yellow)]]
        return None

    def _entity_segments(self, sprite: pygame.sprite.Sprite, state_machine: Any) -> _Segments:
        """One row per datum, every token paired with its display color.

        - header: faction-colored name (the enemy registry type for foes,
          the class name otherwise) plus off-white state
        - ``HP`` row: value tinted by the health ratio
        - ``ZONE`` row (multi-zone sprites only): one ``name xmult`` token per
          zone in its zone color — the world boxes carry no text, the full
          roster lives here where rows never overlap
        - ``ATK`` row (while attacking): gold name, muted phase stats
        - flags row (active flags only, no tag — each flag reads on its
          own): last hit, stagger, OTG, gravity, air, ledge, ``|``-separated
        """
        faction_color = label_color(sprite)
        state_name = state_machine.current_state_name or "None"
        lines: _Segments = [
            [(f"{display_name(sprite)} ", faction_color), (state_name, Colors.off_white)]
        ]
        health = getattr(sprite, "health", None)
        max_health = getattr(sprite, "max_health", None)
        if health is not None and max_health:
            lines.append(
                [
                    ("HP ", LABEL_TAG),
                    (f"{health:.0f}/{max_health:.0f}", _health_colour(health, max_health)),
                ]
            )

        zone_line = self._zone_line(sprite)
        if zone_line is not None:
            lines.append(zone_line)

        attack_line = self._attack_line(sprite)
        if attack_line is not None:
            lines.append(attack_line)

        flags = self._status_flag_tokens(sprite)
        if flags:
            lines.append(join_flag_tokens(flags))
        return lines

    def _zone_line(self, sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]] | None:
        """Zone roster row: ``name xmult`` per zone in its zone color.

        Only for sprites carrying more than one zone worth naming: single
        unnamed neutral zones (the legacy path) add no row. Tags ride the
        token text (``[tag]``) since the world seal is shape-only.
        """
        names = getattr(sprite, "hurtbox_zone_names", None)
        mults = getattr(sprite, "hurtbox_mult", None)
        tags = getattr(sprite, "hurtbox_tags", None)
        zones = getattr(sprite, "hurtboxes", None)
        count = len(tuple(zones)) if zones is not None else 0
        if count <= 1 and not names and not mults:
            return None
        tokens: list[tuple[str, Color]] = [("ZONE ", LABEL_TAG)]
        named = False
        for index in range(count):
            name = names[index] if isinstance(names, tuple) and index < len(names) else ""
            mult = mults[index] if isinstance(mults, tuple) and index < len(mults) else 1.0
            zone_tags = tags[index] if isinstance(tags, tuple) and index < len(tags) else ()
            label = f"{name} x{float(mult):g}" if name else f"x{float(mult):g}"
            if name or float(mult) != 1.0 or zone_tags:
                named = True
            if zone_tags:
                label += f" [{','.join(str(tag) for tag in zone_tags)}]"
            if index > 0:
                tokens.append(("| ", LABEL_SEP))
            tokens.append(
                (label + " ", Colors.debug_hurtbox_zones[index % len(Colors.debug_hurtbox_zones)])
            )
        return tokens if named else None

    def _attack_line(self, sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]] | None:
        """Attack row: gold name plus muted phase stats, ``None`` while idle."""
        combat = getattr(sprite, "combat", None)
        attack_state = getattr(combat, "state", None)
        attack_name = getattr(attack_state, "attack_name", None)
        if attack_name is None:
            return None
        sub_state = getattr(attack_state, "sub_state", None)
        sub_state_name = getattr(sub_state, "value", sub_state)
        phase_index = getattr(attack_state, "phase_index", 0)
        frame_counter = getattr(attack_state, "frame_counter", 0)
        target_count = len(getattr(combat, "targets_hit", ()))
        return [
            ("ATK ", LABEL_TAG),
            (f"{attack_name} ", Colors.gold),
            (
                f"p{phase_index} {sub_state_name}:{frame_counter} hits:{target_count}",
                Colors.light_grey,
            ),
        ]

    @staticmethod
    def _status_flag_tokens(sprite: pygame.sprite.Sprite) -> list[tuple[str, Color]]:
        """Colored status flags for the untagged flags card row (same order as strings)."""
        names = WorldUI._status_flag_strings(sprite)
        colors: dict[str, Color] = {}
        reaction = WorldUI._reaction_flag(sprite)
        if reaction is not None:
            colors[reaction] = (
                Colors.red
                if float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0
                else Colors.dark_red
            )
        stagger = float(getattr(sprite, "stagger_timer", 0.0) or 0.0)
        if stagger > 0:
            colors[f"STAG {stagger:.2f}s"] = Colors.orange
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            current = getattr(state_machine, "current_state_name", None)
            if current == "dizzy":
                colors[f"DIZZY {stagger:.2f}s"] = Colors.gold
        otg = float(getattr(sprite, "otg_timer", 0.0) or 0.0)
        if otg > 0:
            colors[f"OTG {otg:.2f}s"] = Colors.debug_otg
        gravity_scale = float(getattr(sprite, "gravity_scale", 1.0) or 1.0)
        if gravity_scale != 1.0:
            colors[f"GRAV x{gravity_scale:.1f}"] = Colors.debug_juggle
        surface = getattr(sprite, "on_surface", None)
        if isinstance(surface, dict) and not surface.get("floor"):
            colors["AIR"] = Colors.light_grey
        ledge_probe = getattr(sprite, "is_at_ledge", None)
        if callable(ledge_probe) and ledge_probe():
            colors["LEDGE"] = Colors.yellow
        return [(name, colors.get(name, Colors.off_white)) for name in names]

    @staticmethod
    def _reaction_flag(sprite: pygame.sprite.Sprite) -> str | None:
        """Label token for the last hit-reaction cause (kind + freshness).

        Reads the typed ``ReactionStatus`` — never a state-machine name.
        ``HIT`` marks a fresh reaction with its remaining freshness window
        in seconds; ``HIT ... (old)`` marks a stale cause whose freshness
        has expired.
        """
        reaction = getattr(sprite, "reaction_status", None)
        if not isinstance(reaction, ReactionStatus):
            return None
        age = float(getattr(sprite, "reaction_age", 0.0) or 0.0)
        if age > 0:
            return f"HIT {reaction.kind.value} {age:.2f}s"
        return f"HIT {reaction.kind.value} (old)"

    @staticmethod
    def _status_flag_strings(sprite: pygame.sprite.Sprite) -> list[str]:
        """Plain-text status flags backing ``_entity_lines`` (ledge tests, docs)."""
        flags: list[str] = []
        stagger = float(getattr(sprite, "stagger_timer", 0.0) or 0.0)
        if stagger > 0:
            flags.append(f"STAG {stagger:.2f}s")
        state_machine = getattr(sprite, "state_machine", None)
        if state_machine is not None:
            current = getattr(state_machine, "current_state_name", None)
            if current == "dizzy":
                flags.append(f"DIZZY {stagger:.2f}s")
        reaction_flag = WorldUI._reaction_flag(sprite)
        if reaction_flag is not None:
            flags.append(reaction_flag)
        otg = float(getattr(sprite, "otg_timer", 0.0) or 0.0)
        if otg > 0:
            flags.append(f"OTG {otg:.2f}s")
        gravity_scale = float(getattr(sprite, "gravity_scale", 1.0) or 1.0)
        if gravity_scale != 1.0:
            flags.append(f"GRAV x{gravity_scale:.1f}")
        surface = getattr(sprite, "on_surface", None)
        if isinstance(surface, dict) and not surface.get("floor"):
            flags.append("AIR")
        ledge_probe = getattr(sprite, "is_at_ledge", None)
        if callable(ledge_probe) and ledge_probe():
            flags.append("LEDGE")
        return flags

    @staticmethod
    def _entity_lines(sprite: pygame.sprite.Sprite, state_machine: Any) -> list[str]:
        state_name = state_machine.current_state_name or "None"
        head = f"{type(sprite).__name__} {state_name}"
        health = getattr(sprite, "health", None)
        max_health = getattr(sprite, "max_health", None)
        if health is not None and max_health:
            head += f" {health:.0f}/{max_health:.0f}"
        combat = getattr(sprite, "combat", None)
        attack_state = getattr(combat, "state", None)
        attack_name = getattr(attack_state, "attack_name", None)
        detail: list[str] = []
        if attack_name is not None:
            sub_state = getattr(attack_state, "sub_state", None)
            sub_state_name = getattr(sub_state, "value", sub_state)
            phase_index = getattr(attack_state, "phase_index", 0)
            frame_counter = getattr(attack_state, "frame_counter", 0)
            target_count = len(getattr(combat, "targets_hit", ()))
            detail.append(
                f"{attack_name} p{phase_index} {sub_state_name}:{frame_counter} hits:{target_count}"
            )
        flags = WorldUI._status_flag_strings(sprite)
        if flags:
            detail.append(" ".join(flags))
        return [head, *detail]

    @staticmethod
    def _projectile_line(sprite: pygame.sprite.Sprite) -> str:
        velocity = getattr(sprite, "velocity", None)
        vel = f"({velocity.x:.0f},{velocity.y:.0f})" if velocity is not None else "(?,?)"
        life = float(getattr(sprite, "life", 0.0) or 0.0)
        pierce = "pierce" if getattr(getattr(sprite, "config", None), "pierce", False) else "single"
        hits = len(getattr(sprite, "targets_hit", ()))
        faction = getattr(sprite, "faction", "?")
        return f"{type(sprite).__name__} {faction} {vel} {life:.1f}s {pierce} hits:{hits}"

    @staticmethod
    def _label_priority(
        sprite: pygame.sprite.Sprite, anchor: pygame.Rect | pygame.FRect
    ) -> tuple[int, float, float]:
        """Placement order: the player reads first, then top-to-bottom."""
        player_first = 0 if faction(sprite) == "player" else 1
        return (player_first, float(anchor.top), float(anchor.left))

    def _label_clearances(
        self, sprite: pygame.sprite.Sprite, anchor: pygame.Rect | pygame.FRect
    ) -> tuple[int, int]:
        """Vertical room the label card must leave for the tiers below it.

        Returns ``(above_lift, below_drop)`` reserving — whichever applies —
        the health bar and this frame's attack annotations (timeline, zone
        tags, badges) for the sprite. The bar sits above the entity, or
        flips below it near the top of the screen with the annotations
        following it; annotations drawn without a bar (player, dead)
        reserve their own band relative to the sprite. ``(0, 0)`` when
        neither a bar nor annotations exist.
        """
        bar_lift = 0
        bar_drop = 0
        bar = self._health_bar_rect(sprite, anchor)
        if bar is not None:
            # The padded card sticks out self.metrics.label_pad_y below its content box,
            # so the lift reserves bar + gap + padding: backgrounds touch
            # neither the bar nor each other.
            clearance = HEALTH_BAR_HEIGHT + HEALTH_BAR_LABEL_GAP + self.metrics.label_pad_y
            if bar.bottom <= anchor.top:
                bar_lift = clearance
            else:
                bar_drop = clearance
        annotation_rects = self._sink.for_sprite(sprite)
        above_tops = [rect.top for rect in annotation_rects if rect.top < anchor.top]
        below_bottoms = [rect.bottom for rect in annotation_rects if rect.bottom > anchor.bottom]
        ann_lift = 0
        if above_tops:
            # Card background bottom sits ANNOTATION_TIER_GAP above the
            # highest annotation band drawn above the sprite.
            ann_lift = max(
                0,
                int(
                    float(anchor.top)
                    - self.metrics.label_anchor_gap
                    + self.metrics.label_pad_y
                    + self.metrics.tier_gap
                    - min(above_tops)
                ),
            )
        ann_drop = 0
        if below_bottoms:
            ann_drop = max(
                0,
                int(
                    max(below_bottoms)
                    + self.metrics.tier_gap
                    + self.metrics.label_pad_y
                    - float(anchor.bottom)
                    - self.metrics.label_anchor_gap
                ),
            )
        return (max(bar_lift, ann_lift), max(bar_drop, ann_drop))

    def _draw_labels(
        self,
        requests: list[_LabelRequest],
        screen_width: int,
        screen_height: int,
    ) -> None:
        """Draw collected labels, each dodging the ones already placed.

        The health bars drawn for the same sprites are registered as
        obstacles first, then this frame's attack annotation rects: a card
        keeps clear of both like of the other cards, so neither a bar nor
        a timeline can end up painted over a placed card.
        """
        bar_obstacles: list[pygame.Rect] = []
        for _priority, _segments, _color, anchor, _lifts, _drop, sprite in requests:
            bar = self._health_bar_rect(sprite, anchor)
            if bar is not None:
                bar_obstacles.append(
                    bar.inflate(
                        self.metrics.label_bar_clearance * 2, self.metrics.label_bar_clearance * 2
                    )
                )
        placed: list[pygame.Rect] = [
            *bar_obstacles,
            *self._previous_bar_obstacles,
            *self._sink.obstacles,
        ]
        self._previous_bar_obstacles = bar_obstacles
        for _priority, segments, color, anchor, above_lift, below_drop, _sprite in requests:
            rect = self._place_label(
                segments,
                color,
                anchor,
                placed,
                screen_width,
                screen_height,
                above_lift=above_lift,
                below_drop=below_drop,
            )
            if rect is not None:
                placed.append(rect)

    def _place_label(
        self,
        segments: _Segments,
        color: Color,
        anchor: pygame.Rect | pygame.FRect,
        placed: list[pygame.Rect],
        screen_width: int,
        screen_height: int,
        above_lift: int = 0,
        below_drop: int = 0,
    ) -> pygame.Rect | None:
        """Render a label card in the first free slot near its entity.

        The header row uses the compact bold world font; detail rows use the
        compact regular world font. Slots run above the entity (nudging
        upward), then below it (nudging downward). ``above_lift`` reserves
        the health bar stacked between the entity and the card; ``below_drop``
        does the same when the bar flipped under the entity. ``placed``
        holds already-drawn cards *and* the bar/annotation obstacles. Returns the
        padded rect the card occupies, or ``None`` when every slot is taken
        or cannot fit on-screen — a dropped label beats an unreadable stack.
        """
        title_font = self.renderer.world_title_font
        body_font = self.renderer.world_label_font
        header = [self.renderer.render_text(text, title_font, tint) for text, tint in segments[0]]
        rows = [
            [self.renderer.render_text(text, body_font, tint) for text, tint in line]
            for line in segments[1:]
        ]
        row_height = max(
            [s.get_height() for s in header] + [s.get_height() for r in rows for s in r]
        )
        width = max(
            [sum(s.get_width() for s in header)] + [sum(s.get_width() for s in r) for r in rows]
        )
        divider_block = self.metrics.label_divider_top + 1 + self.metrics.label_divider_bottom
        height = (
            row_height * (len(rows) + 1) + self.metrics.label_line_gap * len(rows) + divider_block
            if rows
            else row_height
        )
        base = pygame.Rect(0, 0, width, height)
        base.midbottom = (anchor.centerx, anchor.top - self.metrics.label_anchor_gap - above_lift)
        for label_rect in self._candidate_slots(
            base, anchor, screen_width, screen_height, below_drop=below_drop
        ):
            background_rect = label_rect.inflate(
                self.metrics.label_pad_x * 2, self.metrics.label_pad_y * 2
            )
            if all(not background_rect.colliderect(other) for other in placed):
                self._blit_label(
                    header, rows, row_height, color, label_rect, background_rect, screen_width
                )
                return background_rect
        return None

    def _candidate_slots(
        self,
        base: pygame.Rect,
        anchor: pygame.Rect | pygame.FRect,
        screen_width: int,
        screen_height: int,
        below_drop: int = 0,
    ) -> list[pygame.Rect]:
        """Slots to try, best first: above the entity, then below it.

        A slot that would stick out of the display is shifted back inside
        (never clipped): the padded card must stay fully on-screen with its
        text, so shrinking a slot would just push the text out of its panel.
        """
        below = base.copy()
        below.midtop = (anchor.centerx, anchor.bottom + self.metrics.label_anchor_gap + below_drop)
        slots = [base]
        slots.extend(
            base.move(0, -self.metrics.label_nudge * step)
            for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        slots.append(below)
        slots.extend(
            below.move(0, self.metrics.label_nudge * step)
            for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        kept: list[pygame.Rect] = []
        for slot in slots:
            # The padded card sticks out LABEL_PAD_Y on every side: keep slots
            # whose *card* fits the display, shifted back inside when needed.
            if slot.height + self.metrics.label_pad_y * 2 > screen_height:
                continue  # taller than the display: no fully visible position
            if slot.top - self.metrics.label_pad_y < 0:
                slot.top = self.metrics.label_pad_y
            elif slot.bottom + self.metrics.label_pad_y > screen_height:
                slot.bottom = screen_height - self.metrics.label_pad_y
            slot.left = max(
                self.metrics.label_pad_x,
                min(slot.left, screen_width - slot.width - self.metrics.label_pad_x),
            )
            kept.append(slot)
        return kept

    # -- health bars ----------------------------------------------------------
    #
    # Delegated to `src/ui/world_overlay_bars.py`, which holds the real
    # implementation. These four stay because the label code below needs them
    # to dodge around a bar it never draws (`health_bar_rect` answers "where
    # is the bar for this sprite"), and the renderer reaches the draw pass
    # through the overlay port by this name.
    #
    # The bars are the one part of this file that is **not** debug-only:
    # `Level.draw` calls them before it checks `DEBUG`, so they are painted on
    # every frame of a real game. They are worth not sharing a module with
    # 1800 lines of F1-layer drawing.

    @staticmethod
    def _has_health_bar(sprite: pygame.sprite.Sprite) -> bool:
        """Whether a world-space bar will be drawn for this sprite."""
        return _has_health_bar(sprite)

    def _health_bar_rect(
        self, sprite: pygame.sprite.Sprite, screen_rect: pygame.Rect | pygame.FRect
    ) -> pygame.Rect | None:
        """Where this sprite's bar sits, or None when it has none."""
        return _health_bar_rect(self.surface, sprite, screen_rect)

    def draw_health_bars(
        self,
        entities: Iterable[pygame.sprite.Sprite],
        camera: Camera,
        screen_rects: dict[int, pygame.Rect] | None = None,
    ) -> list[pygame.Rect]:
        """Draw the always-on HP bars; return the rects they occupy."""
        return _draw_health_bars(self.surface, entities, camera, screen_rects)

    def _blit_label(
        self,
        header: list[pygame.Surface],
        rows: list[list[pygame.Surface]],
        row_height: int,
        accent: Color,
        label_rect: pygame.Rect,
        background_rect: pygame.Rect,
        screen_width: int,
    ) -> None:
        """Blit the card: panel, top faction edge, bold header, divider, rows."""
        panel = pygame.Surface(background_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (18, 20, 24, 210), panel.get_rect())
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=1)
        self.surface.blit(panel, background_rect.topleft)
        # Top accent edge in the entity's faction color: a 2 px rule just
        # inside the top border, spanning the card width. It marks the
        # faction at a glance without cutting through the card and its
        # divider the way a full-height side stripe did.
        accent_edge = pygame.Rect(
            background_rect.left + 1,
            background_rect.top + 1,
            background_rect.width - 2,
            2,
        )
        self.surface.fill(accent, accent_edge)
        # Header row (bold).
        cursor_x = label_rect.left
        cursor_y = label_rect.top
        for surface in header:
            self.surface.blit(surface, (cursor_x, cursor_y))
            cursor_x += surface.get_width()
        cursor_y += row_height + self.metrics.label_divider_top
        # Divider rule, inset by the card padding.
        rule_left = max(background_rect.left + self.metrics.label_pad_x, 0)
        rule_right = min(background_rect.right - self.metrics.label_pad_x, screen_width)
        if rule_right > rule_left:
            pygame.draw.line(
                self.surface,
                PANEL_BORDER,
                (rule_left, cursor_y),
                (rule_right, cursor_y),
                1,
            )
        cursor_y += 1 + self.metrics.label_divider_bottom
        for line in rows:
            cursor_x = label_rect.left
            for surface in line:
                self.surface.blit(surface, (cursor_x, cursor_y))
                cursor_x += surface.get_width()
            cursor_y += row_height + self.metrics.label_line_gap
