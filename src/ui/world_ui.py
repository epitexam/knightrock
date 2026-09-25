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
"""

import math
from collections.abc import Iterable
from typing import TYPE_CHECKING

import pygame
import pygame.gfxdraw
from pygame.math import Vector2

from src.combat.shapes import ShapeKind, ShapePose, SweptShape
from src.core.colors import Color, Colors
from src.core.rendering.camera import Camera
from src.core.settings import Debug
from src.entities.components.reaction import VELOCITY_KINDS, ReactionKind, ReactionStatus
from src.states.reaction_states import KNOCKBACK_STATE
from src.ui.panel_renderer import PanelRenderer
from src.ui.styles import PANEL_BORDER, TEXT_CRIT, TEXT_MUTED, TEXT_OK, TEXT_WARN

if TYPE_CHECKING:
    from src.combat.frame_data import PhaseDefinition

#: Separator between tokens inside one label row (``HP``/``ATK``/``FX``).
#: ``Colors.grey`` (80,85,95) is unreadable on the dark card fill, so labels
#: use a slightly brighter grey that still reads as secondary.
LABEL_SEP: Color = Colors.light_grey

#: Tag introducing a detail row (``HP`` / ``ATK`` / ``FX``): muted grey so the
#: *value* carries the color, never the tag.
LABEL_TAG: Color = TEXT_MUTED

#: Velocity vectors show where the sprite heads in this many seconds.
VELOCITY_PREVIEW_S = 0.15

#: Hide near-stationary drift vectors below this speed (px/s).
VELOCITY_MIN_SPEED = 60.0

#: Shortest arrow drawn (px). A slow preview would collapse into a dot, so the
#: shaft stretches just enough for the head to still read as a head;
#: near-stationary drift is already filtered out by ``VELOCITY_MIN_SPEED``.
VELOCITY_MIN_LENGTH = 26.0

#: Arrowhead length: a fraction of the drawn shaft, clamped to
#: ``[VELOCITY_HEAD_MIN, VELOCITY_HEAD_MAX]`` px so a short vector keeps a
#: visible head and a long one does not end in a fat wedge.
VELOCITY_HEAD_RATIO = 0.45
VELOCITY_HEAD_MIN = 7.0
VELOCITY_HEAD_MAX = 15.0

#: Arrowhead half-width as a fraction of the head length (~0.6 reads as a
#: needle, not a blot), capped by ``VELOCITY_HEAD_WIDTH_CAP`` so the head of a
#: short arrow stays proportionate to its shaft instead of turning into a blob.
VELOCITY_HEAD_WIDTH_RATIO = 0.62
VELOCITY_HEAD_WIDTH_CAP = 0.3

#: Shaft widths (px): the neck meets the head, the tail leaves the entity.
#: The taper is what makes the vector read as motion instead of a bar.
VELOCITY_NECK_WIDTH = 4
VELOCITY_TAIL_WIDTH = 2

#: Rounded pivot at the origin (px radius): the arrow visibly departs the
#: entity center instead of starting mid-air.
VELOCITY_TAIL_RADIUS = 3

#: 1 px-ish dark rim stroked under the arrow fill: over a bright sky a plain
#: yellow vector bleeds into the background, the rim keeps the silhouette
#: readable. Half the stroke lands inside the shape and is covered by the fill.
VELOCITY_OUTLINE: Color = (14, 16, 20)
VELOCITY_OUTLINE_WIDTH = 3

#: World margin around the viewport: sprites grazing the edge still draw.
CULL_MARGIN_PX = 64.0

#: Horizontal / vertical padding inside a label card (px per side).
LABEL_PAD_X = 8
LABEL_PAD_Y = 5

#: Gap between the stacked rows of a label card. Rows carry a muted
#: ``HP``/``ATK``/``FX`` tag so the row rhythm stays scannable.
LABEL_LINE_GAP = 5

#: Divider block between the bold header and the detail rows: breathing room
#: above the rule, the 1 px rule itself, then room below it.
LABEL_DIVIDER_TOP = 4
LABEL_DIVIDER_BOTTOM = 5

#: Vertical step a label takes when dodging another label (px). Cards are
#: taller than the legacy one-liners (a two-row card is ~45 px tall with
#: padding), so a dodge may take two steps to clear — the placer tries up to
#: LABEL_MAX_NUDGES steps above, then below, before dropping the label.
LABEL_NUDGE_PX = 28

#: How many dodge steps a label may take above (then below) its entity
#: before being dropped: ~2 label heights of travel is plenty readable.
LABEL_MAX_NUDGES = 6

#: Extra padding between a placed label card and any health bar rectangle:
#: the placer treats bars as obstacles, this keeps a breathing margin on
#: top of the exact rect intersection test.
LABEL_BAR_CLEARANCE = 2

#: Toggleable overlay layers (F1-F5).
OVERLAY_LAYERS = ("boxes", "labels", "velocities", "statics", "panels")

#: Health bar geometry: bar height, gap entity->bar, gap bar->label card.
#: The bar width stays responsive (80% of the on-screen sprite width,
#: clamped to [30, 60] px and to the viewport); only the vertical rhythm
#: is fixed so the stack entity -> bar -> card never overlaps.
HEALTH_BAR_HEIGHT = 6
HEALTH_BAR_ANCHOR_GAP = 8
HEALTH_BAR_LABEL_GAP = 4

#: Gap between an entity edge and its label card when no health bar sits
#: between them (statics, projectiles, or labels layer with bars hidden).
LABEL_ANCHOR_GAP = 8

#: Attack-box outline detail: dashed sweep ghost width (px) and motion arrow
#: head size (px).
SWEEP_GHOST_WIDTH = 1
SWEEP_ARROW_HEAD = 5

#: Smallest per-tick motion that still draws a sweep ghost (px). Below the
#: P1 geometry threshold on purpose: the ghost is render-only, collision
#: thresholds in CombatSettings stay untouched.
SWEEP_DISPLAY_MIN_PX = 1.0

#: Compact badge per hit height: full names would cover the box.
HIT_HEIGHT_BADGES = {
    "high": "HIGH",
    "mid": "MID",
    "low": "LOW",
    "overhead": "OVH",
}

#: Hurtbox zone styling (world px): empty zones (no mult, no tags) keep the
#: legacy thin green outline; boosted zones (mult != 1.0) add a translucent
#: fill + a thicker outline in the zone color; guarded/armored zones (tags)
#: draw a dashed seal in the zone color. Names and mults never paint in the
#: world — the zone card row carries them.
ZONE_FILL_ALPHA = 48
ZONE_OUTLINE_WIDTH = 1
ZONE_BOOST_OUTLINE_WIDTH = 2
ZONE_SEAL_DASH = 4
ZONE_SEAL_GAP = 3
ZONE_SEAL_WIDTH = 2

#: Offensive outline by combat phase: startup telegraphs gold, the active
#: window stays orange, recovery fades to grey.
PHASE_OUTLINE_COLORS = {
    "startup": Colors.gold,
    "active": Colors.debug_attack_box,
    "recovery": Colors.grey,
}

#: Attack header chip geometry (world px): gap between the glyph strip and the
#: timeline bar tucked under it, the phase segments a touch taller than the
#: legacy 4 px hairline so progress reads at range, and a thin divider rule
#: between the chip edge and the leader line landing point.
ATTACK_HEADER_TEXT_GAP = 4
TIMELINE_BAR_HEIGHT = 6
ATTACK_HEADER_RULE_GAP = 2

#: Phase timeline length: per-phase-segment widths per frame, and the cap in
#: world px. A wide attack shouldn't swallow the screen — the bar clamps and
#: the segments shrink to fit, progress stays proportional.
TIMELINE_PX_PER_FRAME = 3
TIMELINE_MAX_WIDTH = 200

#: Vertical gap between the stacked debug tiers around an entity (px):
#: sprite -> health bar -> attack annotations (timeline, zone tags, badges)
#: -> label card. Every tier reserves this much room for the tier above it,
#: so the health bar painted after the overlays can never cover a timeline,
#: and a card can never cover an annotation drawn before it.
ANNOTATION_TIER_GAP = 4

#: Upper bound on the dodge steps an annotation may take upward to clear
#: the tiers below it before it is drawn anyway at the screen edge.
ANNOTATION_MAX_DODGES = 16

#: Shared dark fill of the annotation pills, and the padding inside the
#: attack header chip. The header keeps the card-style backdrop (glyph row +
#: timeline on one card); in-situ tags (zone names, box dots) use the halo
#: instead — they ride their own box, not the stack above the sprite.
ANNOTATION_CHIP_PAD = 3
ANNOTATION_CHIP_FILL = (18, 20, 24, 210)

#: Live combat counters update cadence: refresh every N debug ticks.
METRICS_TICK_DIVISOR = 10

#: Lifetime (s) of the world-space clash marker and its ring radius (px).
CLASH_MARKER_LIFETIME = 0.35
CLASH_MARKER_RADIUS = 18

#: Per-frame TTL decay at the fixed 60 Hz debug cadence.
CLASH_TICK_S = 1.0 / 60.0

#: Unified COMBAT panel: collected once per metrics tick, drawn by the
#: debug panel flow (never blitted at a fixed spot in the world layer).
COMBAT_PANEL_TITLE = "COMBAT"

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


#: Box-index dot geometry (world px): disc radius, dark rim width, white core
#: radius for the hollow (non-first) dots, and inset inside the box corner.
#: The dots are vector-drawn (filled circle + rim), never font glyphs: a
#: ``●``/``○`` glyph at 14 px renders as a blurry blob on most systems.
BOX_DOT_RADIUS = 5
BOX_DOT_RIM_WIDTH = 2
BOX_DOT_CORE_RADIUS = 2
BOX_DOT_INSET = 4

#: Dark rim around the box-index dots: the same card-dark as the halo rings.
BOX_DOT_RIM: Color = (14, 16, 20)


class WorldUI:
    """Render health bars and optional world-space diagnostics."""

    def __init__(self, renderer: PanelRenderer) -> None:
        self.renderer = renderer
        self.display_surface = renderer.display_surface
        self.layers: dict[str, bool] = dict.fromkeys(OVERLAY_LAYERS, True)
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
        #: Attack annotation rects drawn this frame, keyed by sprite id:
        #: the band label cards reserve via ``_label_clearances``.
        self._annotation_rects: dict[int, list[pygame.Rect]] = {}
        #: Every annotation rect drawn this frame, flattened: placement
        #: obstacles for ``_draw_labels`` (any card may overlap any band).
        self._annotation_obstacles: list[pygame.Rect] = []

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
        self._annotation_rects = {}
        self._annotation_obstacles = []
        if not any(self.layers[name] for name in ("boxes", "labels", "velocities", "statics")):
            return
        viewport = self._viewport(camera)
        screen_width = self.display_surface.get_width()

        # Labels are collected first and drawn after the loop so they can
        # dodge each other instead of stacking on shared screen space.
        requests: list[_LabelRequest] = []
        for sprite in all_sprites:
            if type(sprite) is pygame.sprite.Sprite:
                continue  # static tiles: ~900/level, nothing useful to show
            reference = self._debug_reference(sprite)
            if reference is None or not viewport.colliderect(reference):
                continue  # culled: off-screen, not worth a single pixel
            is_static = getattr(sprite, "hitbox", None) is None
            if is_static and not self.layers["statics"]:
                continue
            if self.layers["boxes"]:
                self._draw_boxes(sprite, camera)
            if self.layers["velocities"]:
                self._draw_velocity(sprite, camera)
            request = self._label_request(sprite, reference, is_static, camera)
            if request is not None:
                requests.append(request)

        if requests:
            requests.sort(key=lambda request: request[0])
            self._draw_labels(requests, screen_width, self.display_surface.get_height())

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
            self._label_color(sprite),
            anchor,
            above_lift,
            below_drop,
            sprite,
        )

    @staticmethod
    def _debug_reference(sprite: pygame.sprite.Sprite) -> pygame.FRect | None:
        reference = getattr(sprite, "hitbox", None) or getattr(sprite, "rect", None)
        if reference is None:
            return None
        combat = getattr(sprite, "combat", None)
        rectangles = [pygame.FRect(reference)]
        for name in ("attack_boxes", "swept_attack_boxes"):
            values = getattr(combat, name, ())
            if isinstance(values, tuple):
                rectangles.extend(pygame.FRect(value) for value in values if value is not None)
        anchors = getattr(combat, "attack_anchors", ())
        if isinstance(anchors, tuple):
            rectangles.extend(pygame.FRect(anchor[0], anchor[1], 0.0, 0.0) for anchor in anchors)
        return rectangles[0].unionall(rectangles[1:]) if len(rectangles) > 1 else rectangles[0]

    @staticmethod
    def _viewport(camera: Camera) -> pygame.Rect:
        offset = getattr(camera, "offset", pygame.math.Vector2(0, 0))
        width = float(getattr(camera, "width", 0) or 0)
        height = float(getattr(camera, "height", 0) or 0)
        if width <= 0 or height <= 0:
            surface = pygame.display.get_surface()
            width, height = (surface.get_width(), surface.get_height()) if surface else (0, 0)
        return pygame.Rect(
            offset.x - CULL_MARGIN_PX,
            offset.y - CULL_MARGIN_PX,
            width + 2 * CULL_MARGIN_PX,
            height + 2 * CULL_MARGIN_PX,
        )

    @staticmethod
    def _display_name(sprite: pygame.sprite.Sprite) -> str:
        """Header name: the enemy registry type for foes, the class otherwise.

        Every foe shares the ``Enemy`` class, so the class name says nothing —
        the stored ``enemy_type`` (``"goblin"``, ``"slime"``, ...) does. Other
        factions keep their class name, and typeless enemies fall back to it.
        """
        if WorldUI._faction(sprite) == "enemy":
            return getattr(sprite, "enemy_type", None) or type(sprite).__name__
        return type(sprite).__name__

    @staticmethod
    def _faction(sprite: pygame.sprite.Sprite) -> str | None:
        return getattr(sprite, "faction", None)

    def _hitbox_color(self, sprite: pygame.sprite.Sprite) -> Color:
        faction = self._faction(sprite)
        if faction == "enemy":
            return Colors.red
        if faction == "player":
            return Colors.debug_hitbox
        return Colors.light_grey

    def _label_color(self, sprite: pygame.sprite.Sprite) -> Color:
        if getattr(sprite, "state_machine", None) is None:
            return Colors.yellow  # projectiles
        faction = self._faction(sprite)
        if faction == "enemy":
            return Colors.light_red
        if faction == "player":
            return Colors.light_green
        return Colors.text_muted

    @staticmethod
    def _health_color(health: float, max_health: float) -> Color:
        """HP tint by remaining ratio: green, then warn orange, then crit red."""
        ratio = health / max_health if max_health else 0.0
        if ratio <= 0.25:
            return TEXT_CRIT
        if ratio <= 0.5:
            return TEXT_WARN
        return TEXT_OK

    @staticmethod
    def _hurtbox_zones(
        sprite: pygame.sprite.Sprite, collider: pygame.FRect
    ) -> tuple[pygame.FRect, ...]:
        """Hurt outlines to draw: multi-zone list first, legacy single fallback.

        Zones identical to the collider are skipped (the collider outline
        already covers them); a zone equal to the collider would otherwise
        double-draw the same rectangle.
        """
        zones = getattr(sprite, "hurtboxes", None)
        rects = tuple(zones) if zones is not None else (getattr(sprite, "hurtbox", None),)
        return tuple(zone for zone in rects if zone is not None and zone is not collider)

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
        attack = self._live_attack_text(player)
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

    @staticmethod
    def _live_attack_text(player: object | None) -> str | None:
        """``name substate frame`` for the player's running attack, if any."""
        combat = getattr(player, "combat", None)
        state = getattr(combat, "state", None)
        name = getattr(state, "attack_name", None)
        if not name:
            return None
        sub_state = getattr(state, "sub_state", "")
        phase = getattr(sub_state, "value", sub_state)
        frame = getattr(state, "frame_counter", 0)
        return f"{name} {phase} f{frame}"

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
        radius = round(CLASH_MARKER_RADIUS * (0.5 + progress))
        pygame.draw.circle(self.display_surface, Colors.gold, center, radius, width=2)
        arm = 5
        pygame.draw.line(
            self.display_surface,
            Colors.white,
            (center[0] - arm, center[1] - arm),
            (center[0] + arm, center[1] + arm),
            width=1,
        )
        pygame.draw.line(
            self.display_surface,
            Colors.white,
            (center[0] - arm, center[1] + arm),
            (center[0] + arm, center[1] - arm),
            width=1,
        )

    def _clamp_annotation(self, rect: pygame.Rect) -> pygame.Rect:
        """Shift an annotation rect back inside the display (never clipped)."""
        if rect.right > self.display_surface.get_width():
            rect.right = self.display_surface.get_width()
        if rect.left < 0:
            rect.left = 0
        if rect.top < 0:
            rect.top = 0
        return rect

    def _dodge_annotation(self, rect: pygame.Rect, obstacles: Iterable[pygame.Rect]) -> pygame.Rect:
        """Shift ``rect`` up until it clears every tier drawn below/behind it.

        Each step parks the rect ``ANNOTATION_TIER_GAP`` above the obstacle
        it hit; a step always moves strictly upward, so the loop ends at
        the screen edge where the rect is clamped and drawn anyway — a
        cramped annotation beats a hidden one.
        """
        obstacles = list(obstacles)
        for _ in range(ANNOTATION_MAX_DODGES):
            hit = next((obstacle for obstacle in obstacles if rect.colliderect(obstacle)), None)
            if hit is None:
                break
            rect.bottom = hit.top - ANNOTATION_TIER_GAP
            if rect.top < 0:
                rect.top = 0
                break
        return self._clamp_annotation(rect)

    def _annotation_chip(
        self,
        label: pygame.Surface,
        position: tuple[int, int],
        obstacles: list[pygame.Rect] | None = None,
    ) -> pygame.Rect:
        """Draw a dark pill behind a little world annotation; return its rect.

        The pill is sized around the glyph strip, dodges/clamps like any
        other annotation tier, then paints the card-style fill + border
        with the glyphs on top: tiny text stays legible on any sky instead
        of floating as bare white writing.
        """
        rect = pygame.Rect(position[0], position[1], label.get_width(), label.get_height())
        chip = rect.inflate(ANNOTATION_CHIP_PAD * 2, ANNOTATION_CHIP_PAD * 2)
        if obstacles:
            chip = self._dodge_annotation(chip, obstacles)
        else:
            chip = self._clamp_annotation(chip)
        panel = pygame.Surface(chip.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, ANNOTATION_CHIP_FILL, panel.get_rect())
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=1)
        self.display_surface.blit(panel, chip.topleft)
        self.display_surface.blit(
            label, (chip.x + ANNOTATION_CHIP_PAD, chip.y + ANNOTATION_CHIP_PAD)
        )
        return chip

    def _draw_boxes(self, sprite: pygame.sprite.Sprite, camera: Camera) -> None:
        collider = getattr(sprite, "hitbox", None)
        combat = getattr(sprite, "combat", None)
        attack_boxes = self._offensive_boxes(combat)
        swept_boxes = self._swept_boxes(combat, len(attack_boxes))

        if collider is None:
            reference = getattr(sprite, "rect", None)
            if reference is not None:
                # Hazards, moving platforms, exits: rect-only sprites.
                pygame.draw.rect(
                    self.display_surface,
                    Colors.debug_static,
                    camera.apply(reference),
                    width=1,
                )
            return
        screen = camera.apply(collider)
        # Tier stack for this entity: the health bar (painted after the
        # overlays) plus every annotation already placed this frame. Each
        # text annotation dodges the tiers below it, and is registered so
        # the label cards reserve its band.
        bar = self._health_bar_rect(sprite, screen)
        tiers: list[pygame.Rect] = [bar] if bar is not None else []
        annotations: list[pygame.Rect] = []
        header_rect = self._attack_header_rect(sprite, collider, camera, [*tiers, *annotations])
        if header_rect is not None:
            annotations.append(header_rect)
        pygame.draw.rect(
            self.display_surface,
            self._hitbox_color(sprite),
            camera.apply(collider),
            width=1,
        )
        # P2 multi-zone: shape tells the story, no text. Empty zones keep the
        # legacy thin outline; boosted zones (mult != 1.0) add a translucent
        # fill + a thicker outline; guarded zones (tags) draw a dashed seal.
        # Names and mults live on the label card's zone row, never in the
        # world — nothing to overlap, whatever the zone count.
        zones = self._hurtbox_zones(sprite, collider)
        mults = self._zone_mults(sprite, len(zones))
        tags = self._zone_tags(sprite, len(zones))
        for index, zone in enumerate(zones):
            color = Colors.debug_hurtbox_zones[index % len(Colors.debug_hurtbox_zones)]
            screen_zone = camera.apply(zone)
            mult = mults[index] if index < len(mults) else 1.0
            zone_tags = tags[index] if index < len(tags) else ()
            if mult != 1.0:
                fill = pygame.Surface(
                    (max(1, int(screen_zone.width)), max(1, int(screen_zone.height))),
                    pygame.SRCALPHA,
                )
                fill.fill((*color, ZONE_FILL_ALPHA))
                self.display_surface.blit(fill, (screen_zone.x, screen_zone.y))
                pygame.draw.rect(
                    self.display_surface,
                    color,
                    screen_zone,
                    width=ZONE_BOOST_OUTLINE_WIDTH,
                )
            else:
                pygame.draw.rect(
                    self.display_surface,
                    color,
                    screen_zone,
                    width=ZONE_OUTLINE_WIDTH,
                )
            if zone_tags:
                self._draw_zone_seal(screen_zone, color)
        annotations.extend(
            self._draw_offensive_boxes(
                sprite,
                collider,
                combat,
                attack_boxes,
                swept_boxes,
                camera,
                [*tiers, *annotations],
            )
        )
        # Phase 5 markers: OTG guard (cyan) and juggle gravity (purple).
        if float(getattr(sprite, "otg_timer", 0.0) or 0.0) > 0:
            pygame.draw.rect(
                self.display_surface,
                Colors.debug_otg,
                camera.apply(collider),
                width=3,
            )
        if float(getattr(sprite, "gravity_scale", 1.0) or 1.0) != 1.0:
            pygame.draw.rect(
                self.display_surface,
                Colors.debug_juggle,
                camera.apply(collider),
                width=2,
            )
        self._register_annotations(sprite, annotations)

    def _register_annotations(self, sprite: pygame.sprite.Sprite, rects: list[pygame.Rect]) -> None:
        """Record an entity's annotation rects for this frame.

        The rects feed both the label-card obstacles (``_draw_labels``) and
        the card clearances (``_label_clearances``), so a card reserves the
        annotation band drawn between the entity and the card slot.
        """
        if not rects:
            return
        self._annotation_rects[id(sprite)] = list(rects)
        self._annotation_obstacles.extend(rects)

    @staticmethod
    def _zone_mults(sprite: pygame.sprite.Sprite, count: int) -> tuple[float, ...]:
        """Per-zone damage mults, neutral 1.0 past the known list."""
        mults = getattr(sprite, "hurtbox_mult", None)
        if not isinstance(mults, tuple):
            return (1.0,) * count
        values = tuple(float(mult) for mult in mults[:count])
        return values + (1.0,) * (count - len(values))

    @staticmethod
    def _zone_tags(sprite: pygame.sprite.Sprite, count: int) -> tuple[tuple[str, ...], ...]:
        """Per-zone invulnerability tags, empty past the known list."""
        tags = getattr(sprite, "hurtbox_tags", None)
        if not isinstance(tags, tuple):
            return ((),) * count
        values = tuple(tuple(zone) for zone in tags[:count])
        return values + ((),) * (count - len(values))

    def _draw_zone_seal(self, screen: pygame.FRect, color: Color) -> None:
        """Dashed inset seal for guarded/armored zones (tags present)."""
        x, y, w, h = screen.x, screen.y, screen.width, screen.height
        inset = ZONE_BOOST_OUTLINE_WIDTH + 1
        inner = pygame.FRect(x + inset, y + inset, max(0.0, w - inset * 2), max(0.0, h - inset * 2))
        if inner.width <= 0 or inner.height <= 0:
            return
        step = ZONE_SEAL_DASH + ZONE_SEAL_GAP
        cursor = inner.x
        while cursor < inner.x + inner.width:
            end = min(cursor + ZONE_SEAL_DASH, inner.x + inner.width)
            pygame.draw.line(
                self.display_surface, color, (cursor, inner.y), (end, inner.y), ZONE_SEAL_WIDTH
            )
            pygame.draw.line(
                self.display_surface,
                color,
                (cursor, inner.y + inner.height),
                (end, inner.y + inner.height),
                ZONE_SEAL_WIDTH,
            )
            cursor += step
        cursor = inner.y
        while cursor < inner.y + inner.height:
            end = min(cursor + ZONE_SEAL_DASH, inner.y + inner.height)
            pygame.draw.line(
                self.display_surface, color, (inner.x, cursor), (inner.x, end), ZONE_SEAL_WIDTH
            )
            pygame.draw.line(
                self.display_surface,
                color,
                (inner.x + inner.width, cursor),
                (inner.x + inner.width, end),
                ZONE_SEAL_WIDTH,
            )
            cursor += step

    @staticmethod
    def _offensive_hit(combat: object) -> object | None:
        phase = getattr(combat, "current_phase", None)
        return getattr(phase, "hit", None)

    def _offensive_badges(self, combat: object) -> tuple[str, ...]:
        hit = self._offensive_hit(combat)
        if hit is None:
            return ()
        badges: list[str] = []
        shapes = self._offensive_shapes(combat)
        if shapes:
            badges.append(shapes[0].kind.value.upper())
        priority = int(getattr(hit, "priority", 0) or 0)
        if priority > 0:
            badges.append(f"P{priority}")
        if bool(getattr(hit, "unblockable", False)):
            badges.append("UBL")
        height = str(getattr(hit, "height", "mid") or "mid")
        if height != "mid":
            badges.append(HIT_HEIGHT_BADGES.get(height, height.upper()))
        return tuple(badges)

    def _offensive_outline(self, combat: object) -> Color:
        state = getattr(combat, "state", None)
        phase_name = getattr(getattr(state, "sub_state", None), "value", None)
        if isinstance(phase_name, str):
            return PHASE_OUTLINE_COLORS.get(phase_name, Colors.debug_attack_box)
        return Colors.debug_attack_box

    @staticmethod
    def _offensive_boxes(combat: object) -> tuple:
        boxes = getattr(combat, "attack_boxes", None)
        if boxes is None:
            legacy_box = getattr(combat, "attack_box", None)
            return (legacy_box,) if legacy_box is not None else ()
        return tuple(boxes)

    @staticmethod
    def _box_moved(swept: pygame.FRect, current: pygame.FRect) -> bool:
        swept_center = Vector2(swept.centerx, swept.centery)
        current_center = Vector2(current.centerx, current.centery)
        if swept_center.distance_to(current_center) >= SWEEP_DISPLAY_MIN_PX:
            return True
        return (
            abs(swept.width - current.width) >= SWEEP_DISPLAY_MIN_PX
            or abs(swept.height - current.height) >= SWEEP_DISPLAY_MIN_PX
        )

    @staticmethod
    def _swept_boxes(combat: object, count: int) -> tuple:
        swept = getattr(combat, "swept_attack_boxes", None)
        if callable(swept):
            boxes = tuple(swept())
            if len(boxes) == count:
                return boxes
        return (None,) * count

    @staticmethod
    def _swept_shapes(combat: object, count: int) -> tuple[SweptShape | None, ...]:
        shapes = getattr(combat, "swept_attack_shapes", ())
        if not isinstance(shapes, tuple) or len(shapes) != count:
            return (None,) * count
        return shapes

    @staticmethod
    def _attack_anchors(combat: object) -> tuple[tuple[float, float], ...]:
        anchors = getattr(combat, "attack_anchors", ())
        return tuple(anchors) if isinstance(anchors, tuple) else ()

    @staticmethod
    def _offensive_shapes(combat: object) -> tuple[ShapePose, ...]:
        shapes = getattr(combat, "attack_shapes", ())
        return tuple(shapes) if isinstance(shapes, tuple) else ()

    def _draw_shape_once(
        self,
        shape: ShapePose,
        color: Color,
        camera: Camera,
        width: int,
    ) -> None:
        center = camera.apply(
            pygame.FRect(
                shape.position[0] - shape.size[0] / 2.0,
                shape.position[1] - shape.size[1] / 2.0,
                shape.size[0],
                shape.size[1],
            )
        ).center
        if shape.kind is ShapeKind.CIRCLE:
            pygame.draw.circle(self.display_surface, color, center, int(shape.size[0] / 2.0), width)
            return
        if shape.kind is ShapeKind.CAPSULE:
            radians = math.radians(shape.angle)
            half_length = shape.size[0] / 2.0
            offset = (
                math.cos(radians) * half_length,
                math.sin(radians) * half_length,
            )
            start = (round(center[0] - offset[0]), round(center[1] - offset[1]))
            end = (round(center[0] + offset[0]), round(center[1] + offset[1]))
            diameter = max(1, int(shape.size[1]))
            pygame.draw.line(self.display_surface, color, start, end, diameter)
            radius = diameter / 2.0
            pygame.draw.circle(self.display_surface, color, start, max(1, int(radius)), width)
            pygame.draw.circle(self.display_surface, color, end, max(1, int(radius)), width)
            return
        if shape.kind is ShapeKind.OBB:
            radians = math.radians(shape.angle)
            cosine = math.cos(radians)
            sine = math.sin(radians)
            half_width = shape.size[0] / 2.0
            half_height = shape.size[1] / 2.0
            points = []
            for local_x, local_y in (
                (-half_width, -half_height),
                (half_width, -half_height),
                (half_width, half_height),
                (-half_width, half_height),
            ):
                points.append(
                    (
                        int(round(center[0] + local_x * cosine - local_y * sine)),
                        int(round(center[1] + local_x * sine + local_y * cosine)),
                    )
                )
            pygame.draw.polygon(self.display_surface, color, points, width)
            return
        pygame.draw.rect(
            self.display_surface,
            color,
            camera.apply(
                pygame.FRect(
                    shape.position[0] - shape.size[0] / 2.0,
                    shape.position[1] - shape.size[1] / 2.0,
                    shape.size[0],
                    shape.size[1],
                )
            ),
            width=width,
        )

    def _draw_shape(self, shape: ShapePose, color: Color, camera: Camera, width: int = 2) -> None:
        self._draw_shape_once(shape, Colors.debug_shape_outline, camera, width + 2)
        self._draw_shape_once(shape, color, camera, width)

    def _draw_anchor(self, point: tuple[float, float], camera: Camera) -> None:
        center = camera.apply(pygame.FRect(point[0], point[1], 0.0, 0.0)).center
        radius = 5
        pygame.draw.line(
            self.display_surface,
            Colors.debug_anchor,
            (round(center[0] - radius), round(center[1])),
            (round(center[0] + radius), round(center[1])),
            1,
        )
        pygame.draw.line(
            self.display_surface,
            Colors.debug_anchor,
            (round(center[0]), round(center[1] - radius)),
            (round(center[0]), round(center[1] + radius)),
            1,
        )

    def _draw_attack_geometry(
        self,
        attack_box: pygame.FRect,
        swept: pygame.FRect | None,
        shape: ShapePose | None,
        swept_shape: SweptShape | None,
        anchor: tuple[float, float] | None,
        outline: Color,
        camera: Camera,
    ) -> None:
        advanced = shape is not None and shape.kind is not ShapeKind.AABB
        if advanced and shape is not None:
            self._draw_dashed_rect(camera.apply(attack_box), Colors.debug_broadphase)
        if swept is not None and swept != attack_box and self._box_moved(swept, attack_box):
            self._draw_dashed_rect(camera.apply(swept), Colors.debug_sweep)
            self._draw_motion_arrow(swept, attack_box, camera)
        if advanced and swept_shape is not None and swept_shape.previous is not None:
            previous = swept_shape.previous
            self._draw_shape_once(previous, Colors.debug_sweep, camera, 1)
            self._draw_motion_arrow(
                pygame.FRect(
                    previous.position[0] - previous.size[0] / 2.0,
                    previous.position[1] - previous.size[1] / 2.0,
                    previous.size[0],
                    previous.size[1],
                ),
                attack_box,
                camera,
            )
        if advanced and shape is not None:
            self._draw_shape(shape, outline, camera)
        else:
            pygame.draw.rect(self.display_surface, outline, camera.apply(attack_box), width=2)
        if anchor is not None:
            self._draw_anchor(anchor, camera)

    def _draw_offensive_boxes(
        self,
        sprite: pygame.sprite.Sprite,
        collider: pygame.FRect | None,
        combat: object,
        attack_boxes: tuple,
        swept_boxes: tuple,
        camera: Camera,
        obstacles: list[pygame.Rect] | None = None,
    ) -> list[pygame.Rect]:
        """Outline the attack boxes; dot in-situ indices; spray halo ghosts.

        Box indices ride their own box (a haloed ``●`` top-left corner of each
        box, ``○`` past the first) instead of floating in the tier stack: one
        header chip per attacker, no constellation of pills. Returns the
        in-situ dot rects so the caller can register them for label-card
        placement.
        """
        outline = self._offensive_outline(combat)
        shapes = self._offensive_shapes(combat)
        swept_shapes = self._swept_shapes(combat, len(attack_boxes))
        anchors = self._attack_anchors(combat)
        drawn: list[pygame.Rect] = []
        for index, attack_box in enumerate(attack_boxes):
            swept = swept_boxes[index] if index < len(swept_boxes) else None
            shape = shapes[index] if index < len(shapes) else None
            swept_shape = swept_shapes[index] if index < len(swept_shapes) else None
            anchor = anchors[index] if index < len(anchors) else None
            self._draw_attack_geometry(
                attack_box,
                swept,
                shape,
                swept_shape,
                anchor,
                outline,
                camera,
            )
            screen_box = camera.apply(attack_box)
            drawn.append(
                self._in_situ_dot(
                    (int(screen_box.x) + BOX_DOT_INSET, int(screen_box.y) + BOX_DOT_INSET),
                    outline,
                    filled=index == 0,
                )
            )
        return drawn

    def _draw_dashed_rect(self, screen: pygame.FRect, color: Color) -> None:
        x, y, width, height = screen.x, screen.y, screen.width, screen.height
        for start, end in self._dashed_edges(x, y, width, height):
            pygame.draw.line(self.display_surface, color, start, end, SWEEP_GHOST_WIDTH)

    @staticmethod
    def _dashed_edges(
        x: float, y: float, width: float, height: float
    ) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
        step = 2 * SWEEP_GHOST_WIDTH + 2
        edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
        cursor = x
        while cursor < x + width:
            end = min(cursor + SWEEP_GHOST_WIDTH + 2, x + width)
            edges.append(((cursor, y), (end, y)))
            edges.append(((cursor, y + height), (end, y + height)))
            cursor += step
        cursor = y
        while cursor < y + height:
            end = min(cursor + SWEEP_GHOST_WIDTH + 2, y + height)
            edges.append(((x, cursor), (x, end)))
            edges.append(((x + width, cursor), (x + width, end)))
            cursor += step
        return tuple(edges)

    def _draw_motion_arrow(
        self, swept: pygame.FRect, current: pygame.FRect, camera: Camera
    ) -> None:
        start = camera.apply(swept).center
        end = camera.apply(current).center
        delta = Vector2(end) - Vector2(start)
        if delta.length_squared() < 1.0:
            return
        pygame.draw.line(self.display_surface, Colors.debug_attack_box, start, end)
        direction = delta.normalize()
        normal = Vector2(-direction.y, direction.x)
        tip = Vector2(end)
        left = tip - direction * SWEEP_ARROW_HEAD + normal * SWEEP_ARROW_HEAD
        right = tip - direction * SWEEP_ARROW_HEAD - normal * SWEEP_ARROW_HEAD
        pygame.draw.polygon(
            self.display_surface, Colors.debug_attack_box, [tuple(tip), tuple(left), tuple(right)]
        )

    @staticmethod
    def _timeline_progress(state: object, sub_state: object, phase: PhaseDefinition) -> int:
        frame = int(getattr(state, "frame_counter", 0) or 0)
        startup = int(getattr(phase, "startup_frames", 0) or 0)
        active = int(getattr(phase, "active_frames", 0) or 0)
        recovery = int(getattr(phase, "recovery_frames", 0) or 0)
        if sub_state == "startup":
            return min(frame, startup) * TIMELINE_PX_PER_FRAME
        if sub_state == "active":
            return (startup + min(frame, active)) * TIMELINE_PX_PER_FRAME
        return (startup + active + min(frame, recovery)) * TIMELINE_PX_PER_FRAME

    def _draw_velocity(self, sprite: pygame.sprite.Sprite, camera: Camera) -> None:
        velocity = getattr(sprite, "velocity", None)
        if velocity is None:
            return
        try:
            vx, vy = float(velocity.x), float(velocity.y)
        except AttributeError, TypeError:
            return
        if vx * vx + vy * vy < VELOCITY_MIN_SPEED * VELOCITY_MIN_SPEED:
            return
        origin = getattr(sprite, "hitbox", None) or getattr(sprite, "rect", None)
        if origin is None:
            return
        color = Colors.debug_velocity
        if self._is_parry_flash(sprite):
            color = Colors.gold
        elif self._is_reaction_push(sprite):
            color = Colors.red  # reaction push vector, not locomotion
        self._draw_velocity_arrow(Vector2(camera.apply(origin).center), Vector2(vx, vy), color)

    def _draw_velocity_arrow(self, start: Vector2, velocity: Vector2, color: Color) -> None:
        """Paint one velocity preview: rim, filled tapered shaft and arrowhead.

        Geometry recap — the tail leaves the entity thinner than the neck, the
        barbs flare at ``head_length`` from the tip, and the pivot dot marks
        where the sprite actually is. The dark rim is stroked first, then the
        colour fill covers its inner half, and an anti-aliased pass smooths the
        fill boundary on top (debug-only cost: a handful of visible sprites).
        """
        delta = velocity * VELOCITY_PREVIEW_S
        length = delta.length()
        if length <= 0.0:
            return
        direction = delta / length
        drawn_length = max(length, VELOCITY_MIN_LENGTH)
        head_length = min(
            max(drawn_length * VELOCITY_HEAD_RATIO, VELOCITY_HEAD_MIN),
            VELOCITY_HEAD_MAX,
            drawn_length,
        )
        points = arrow_outline(
            start,
            direction,
            drawn_length,
            head_length,
            min(head_length * VELOCITY_HEAD_WIDTH_RATIO, drawn_length * VELOCITY_HEAD_WIDTH_CAP),
        )
        pygame.draw.polygon(
            self.display_surface, VELOCITY_OUTLINE, points, width=VELOCITY_OUTLINE_WIDTH
        )
        pygame.draw.polygon(self.display_surface, color, points)
        pygame.gfxdraw.aapolygon(self.display_surface, points, color)

        pivot = (round(start.x), round(start.y))
        pygame.draw.circle(
            self.display_surface,
            VELOCITY_OUTLINE,
            pivot,
            VELOCITY_TAIL_RADIUS + VELOCITY_OUTLINE_WIDTH // 2,
        )
        pygame.draw.circle(self.display_surface, color, pivot, VELOCITY_TAIL_RADIUS)
        pygame.gfxdraw.aacircle(self.display_surface, *pivot, VELOCITY_TAIL_RADIUS, color)

    @staticmethod
    def _is_parry_flash(sprite: pygame.sprite.Sprite) -> bool:
        status = getattr(sprite, "reaction_status", None)
        if not isinstance(status, ReactionStatus):
            return False
        if status.kind is not ReactionKind.PARRIED:
            return False
        return float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0.0

    @staticmethod
    def _is_reaction_push(sprite: pygame.sprite.Sprite) -> bool:
        """Whether the vector is a hit reaction's push (red), not locomotion.

        The typed ``ReactionStatus`` cause stays the gate — a bare state name
        can never colour a vector — but it qualifies through two windows:

        - *fresh cause* (``reaction_age > 0``): the hit just landed, so the
          vector is the impulse it applied;
        - *carried by the cause*: the entity is still in ``KNOCKBACK_STATE``
          with a velocity-kind cause. A launch stays airborne far longer than
          the ``ReactionMark`` freshness window (up to
          ``Combat.KNOCKBACK_MAX_DURATION``) and its vector still comes from
          that knockback — wall bounce, directional influence and friction
          all rewrite it without re-arming the cause.

        Walking, dashing, an AI chase or the tail of a resolved knockback read
        as locomotion (yellow).
        """
        status = getattr(sprite, "reaction_status", None)
        if not isinstance(status, ReactionStatus) or status.kind not in VELOCITY_KINDS:
            return False
        if float(getattr(sprite, "reaction_age", 0.0) or 0.0) > 0.0:
            return True
        state_machine = getattr(sprite, "state_machine", None)
        return getattr(state_machine, "current_state_name", None) == KNOCKBACK_STATE

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

    def _entity_segments(self, sprite: pygame.sprite.Sprite, state_machine) -> _Segments:
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
        faction_color = self._label_color(sprite)
        state_name = state_machine.current_state_name or "None"
        lines: _Segments = [
            [(f"{self._display_name(sprite)} ", faction_color), (state_name, Colors.off_white)]
        ]
        health = getattr(sprite, "health", None)
        max_health = getattr(sprite, "max_health", None)
        if health is not None and max_health:
            lines.append(
                [
                    ("HP ", LABEL_TAG),
                    (f"{health:.0f}/{max_health:.0f}", self._health_color(health, max_health)),
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

    def _in_situ_dot(
        self,
        position: tuple[int, int],
        color: Color,
        filled: bool,
    ) -> pygame.Rect:
        """Box-index dot: vector disc in the box corner, ``filled`` = first box.

        An attack may carry several boxes at once; the dot says which is
        which, in code order: the first box (index 0, the one the header's
        leader line points at) gets the solid disc, later boxes the ring.
        The disc is drawn with primitives — dark rim, phase-colored face,
        white core punched out for non-first boxes — never a ``●``/``○``
        font glyph, which rasterizes as a blurry blob at 14 px. The dot
        sits inside its own box corner (``BOX_DOT_INSET``), so it can never
        collide with the header, the card, or a sibling dot.
        """
        center = (
            position[0] + BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH,
            position[1] + BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH,
        )
        pygame.draw.circle(
            self.display_surface,
            BOX_DOT_RIM,
            center,
            BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH,
        )
        pygame.draw.circle(self.display_surface, color, center, BOX_DOT_RADIUS)
        if not filled:
            pygame.draw.circle(self.display_surface, Colors.off_white, center, BOX_DOT_CORE_RADIUS)
        side = (BOX_DOT_RADIUS + BOX_DOT_RIM_WIDTH) * 2 + 1
        return pygame.Rect(center[0] - side // 2, center[1] - side // 2, side, side)

    def _attack_header_rect(
        self,
        sprite: pygame.sprite.Sprite,
        collider: pygame.FRect,
        camera: Camera,
        obstacles: list[pygame.Rect],
    ) -> pygame.Rect | None:
        """One chip naming the live attack: name, phase, badges.

        Merges the scattered ``ATK`` pill + ``b{i}`` ids + gold badges into a
        single header in the tier stack: glyphs on one row, the phase timeline
        tucked underneath on the same card, a 1 px leader line to the first
        attack box when boxes exist. ``None`` while idle (no name, no phase).
        """
        combat = getattr(sprite, "combat", None)
        state = getattr(combat, "state", None)
        attack_name = getattr(state, "attack_name", None)
        phase: PhaseDefinition | None = getattr(combat, "current_phase", None)
        attack_boxes = self._offensive_boxes(combat)
        if attack_name is None or phase is None:
            return None
        sub_state = getattr(state, "sub_state", None)
        frame_counter = int(getattr(state, "frame_counter", 0) or 0)
        phase_value = getattr(sub_state, "value", sub_state)
        phase_name = str(phase_value)
        badges = " ".join(self._offensive_badges(combat))
        tokens: list[tuple[str, Color]] = [
            (f"{attack_name} ", Colors.gold),
            (f"{phase_name}:{frame_counter}", Colors.off_white),
        ]
        if badges:
            tokens.append((f" {badges}", Colors.gold))
        glyphs = [
            self.renderer.render_text(text, self.renderer.world_title_font, color)
            for text, color in tokens
        ]
        text_w = sum(glyph.get_width() for glyph in glyphs)
        title_h = max(glyph.get_height() for glyph in glyphs)
        tl_widths, tl_rect_w = self._attack_timeline_widths(phase, state, phase_name)
        chip_text_w = text_w + ANNOTATION_CHIP_PAD * 2
        chip_tl_w = tl_rect_w + ANNOTATION_CHIP_PAD * 2
        chip_w = max(chip_text_w, chip_tl_w)
        chip_h = (
            ANNOTATION_CHIP_PAD
            + title_h
            + ATTACK_HEADER_TEXT_GAP
            + TIMELINE_BAR_HEIGHT
            + ANNOTATION_CHIP_PAD
        )
        screen = camera.apply(collider)
        bar = self._health_bar_rect(sprite, screen)
        if bar is not None and bar.bottom <= screen.top:
            anchor_y = bar.top - ANNOTATION_TIER_GAP
        elif bar is not None:
            anchor_y = bar.bottom + ANNOTATION_TIER_GAP + chip_h
        else:
            anchor_y = int(screen.top) - ANNOTATION_TIER_GAP
        chip = pygame.Rect(int(screen.x), int(anchor_y - chip_h), chip_w, chip_h)
        chip = self._dodge_annotation(chip, obstacles)
        panel = pygame.Surface(chip.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, ANNOTATION_CHIP_FILL, panel.get_rect())
        pygame.draw.rect(panel, PANEL_BORDER, panel.get_rect(), width=1)
        self.display_surface.blit(panel, chip.topleft)
        cursor = chip.x + (chip_w - text_w) // 2
        for glyph in glyphs:
            self.display_surface.blit(glyph, (cursor, chip.y + ANNOTATION_CHIP_PAD))
            cursor += glyph.get_width()
        tl_x = chip.x + max(0, (chip_w - tl_rect_w) // 2)
        tl_y = chip.y + ANNOTATION_CHIP_PAD + title_h + ATTACK_HEADER_TEXT_GAP
        self._paint_attack_timeline(tl_x, tl_y, phase, tl_widths, state, phase_name)
        if attack_boxes:
            first = camera.apply(attack_boxes[0])
            pygame.draw.line(
                self.display_surface,
                PANEL_BORDER,
                (chip.centerx, chip.bottom + ATTACK_HEADER_RULE_GAP),
                (int(first.centerx), int(first.top)),
                1,
            )
        return chip

    def _attack_timeline_widths(
        self,
        phase: PhaseDefinition,
        state: object,
        sub_state: object,
    ) -> tuple[list[tuple[int, Color]], int]:
        """Phase segment widths, shrunk to ``TIMELINE_MAX_WIDTH``; total width."""
        startup = int(getattr(phase, "startup_frames", 0) or 0)
        active = int(getattr(phase, "active_frames", 0) or 0)
        recovery = int(getattr(phase, "recovery_frames", 0) or 0)
        raw = [
            max(1, startup * TIMELINE_PX_PER_FRAME),
            max(1, active * TIMELINE_PX_PER_FRAME),
            max(1, recovery * TIMELINE_PX_PER_FRAME),
        ]
        total = sum(raw)
        if total > TIMELINE_MAX_WIDTH:
            scaled = [max(1, round(width * TIMELINE_MAX_WIDTH / total)) for width in raw]
            widths = scaled
        else:
            widths = raw
        colors = (Colors.gold, Colors.debug_attack_box, Colors.light_grey)
        return [(width, color) for width, color in zip(widths, colors, strict=True)], sum(widths)

    def _paint_attack_timeline(
        self,
        x: int,
        y: int,
        phase: PhaseDefinition,
        widths: list[tuple[int, Color]],
        state: object,
        sub_state: object,
    ) -> None:
        """Paint the phase segments at ``(x, y)`` with a progress outline."""
        cursor = x
        for width, color in widths:
            pygame.draw.rect(
                self.display_surface,
                color,
                pygame.Rect(cursor, y, width, TIMELINE_BAR_HEIGHT),
            )
            cursor += width
        filled = self._timeline_progress(state, sub_state, phase)
        pygame.draw.rect(
            self.display_surface,
            Colors.off_white,
            pygame.Rect(x, y, min(filled, cursor - x), TIMELINE_BAR_HEIGHT),
            width=1,
        )

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
    def _entity_lines(sprite: pygame.sprite.Sprite, state_machine) -> list[str]:
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
        player_first = 0 if WorldUI._faction(sprite) == "player" else 1
        return (player_first, float(anchor.top), float(anchor.left))

    @staticmethod
    def _has_health_bar(sprite: pygame.sprite.Sprite) -> bool:
        """Whether ``draw_health_bars`` will draw a bar for this sprite.

        The player is excluded: its HP is read on the screen HUD (UI-7), a
        world-space bar above it would be redundant. The gate sits here so
        the debug label cards stop reserving room for a bar never drawn.
        """
        if WorldUI._faction(sprite) == "player":
            return False
        if getattr(sprite, "is_dead", False):
            return False
        if not getattr(sprite, "max_health", 0):
            return False
        return (
            getattr(sprite, "hitbox", None) is not None or getattr(sprite, "rect", None) is not None
        )

    def _health_bar_rect(
        self, sprite: pygame.sprite.Sprite, screen_rect: pygame.Rect | pygame.FRect
    ) -> pygame.Rect | None:
        """Responsive health bar rect: width follows the sprite, clamped.

        The bar sits ``HEALTH_BAR_ANCHOR_GAP`` above the entity; near the
        top of the screen (no room above) it flips below the entity so it
        stays visible instead of clipping. Returns ``None`` for sprites
        without a bar (dead, no ``max_health``, statics).
        """
        if not self._has_health_bar(sprite):
            return None
        screen_width = self.display_surface.get_width()
        screen_height = self.display_surface.get_height()
        bar_width = max(30, min(float(screen_rect.width) * 0.8, 60))
        bar_x = screen_rect.centerx - bar_width / 2
        bar_x = min(max(bar_x, 0), max(0, screen_width - bar_width))
        bar_y = float(screen_rect.top) - HEALTH_BAR_ANCHOR_GAP - HEALTH_BAR_HEIGHT
        if bar_y < 0:
            bar_y = float(screen_rect.bottom) + HEALTH_BAR_ANCHOR_GAP
            if bar_y + HEALTH_BAR_HEIGHT > screen_height:
                return None
        return pygame.Rect(int(bar_x), int(bar_y), int(bar_width), HEALTH_BAR_HEIGHT)

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
            # The padded card sticks out LABEL_PAD_Y below its content box,
            # so the lift reserves bar + gap + padding: backgrounds touch
            # neither the bar nor each other.
            clearance = HEALTH_BAR_HEIGHT + HEALTH_BAR_LABEL_GAP + LABEL_PAD_Y
            if bar.bottom <= anchor.top:
                bar_lift = clearance
            else:
                bar_drop = clearance
        annotation_rects = self._annotation_rects.get(id(sprite), ())
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
                    - LABEL_ANCHOR_GAP
                    + LABEL_PAD_Y
                    + ANNOTATION_TIER_GAP
                    - min(above_tops)
                ),
            )
        ann_drop = 0
        if below_bottoms:
            ann_drop = max(
                0,
                int(
                    max(below_bottoms)
                    + ANNOTATION_TIER_GAP
                    + LABEL_PAD_Y
                    - float(anchor.bottom)
                    - LABEL_ANCHOR_GAP
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
                bar_obstacles.append(bar.inflate(LABEL_BAR_CLEARANCE * 2, LABEL_BAR_CLEARANCE * 2))
        placed: list[pygame.Rect] = [
            *bar_obstacles,
            *self._previous_bar_obstacles,
            *self._annotation_obstacles,
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
        divider_block = LABEL_DIVIDER_TOP + 1 + LABEL_DIVIDER_BOTTOM
        height = (
            row_height * (len(rows) + 1) + LABEL_LINE_GAP * len(rows) + divider_block
            if rows
            else row_height
        )
        base = pygame.Rect(0, 0, width, height)
        base.midbottom = (anchor.centerx, anchor.top - LABEL_ANCHOR_GAP - above_lift)
        for label_rect in self._candidate_slots(
            base, anchor, screen_width, screen_height, below_drop=below_drop
        ):
            background_rect = label_rect.inflate(LABEL_PAD_X * 2, LABEL_PAD_Y * 2)
            if all(not background_rect.colliderect(other) for other in placed):
                self._blit_label(
                    header, rows, row_height, color, label_rect, background_rect, screen_width
                )
                return background_rect
        return None

    @staticmethod
    def _candidate_slots(
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
        below.midtop = (anchor.centerx, anchor.bottom + LABEL_ANCHOR_GAP + below_drop)
        slots = [base]
        slots.extend(
            base.move(0, -LABEL_NUDGE_PX * step) for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        slots.append(below)
        slots.extend(
            below.move(0, LABEL_NUDGE_PX * step) for step in range(1, LABEL_MAX_NUDGES + 1)
        )
        kept: list[pygame.Rect] = []
        for slot in slots:
            # The padded card sticks out LABEL_PAD_Y px on every side: keep slots
            # whose *card* fits the display, shifted back inside when needed.
            if slot.height + LABEL_PAD_Y * 2 > screen_height:
                continue  # taller than the display: no fully visible position
            if slot.top - LABEL_PAD_Y < 0:
                slot.top = LABEL_PAD_Y
            elif slot.bottom + LABEL_PAD_Y > screen_height:
                slot.bottom = screen_height - LABEL_PAD_Y
            slot.left = max(LABEL_PAD_X, min(slot.left, screen_width - slot.width - LABEL_PAD_X))
            kept.append(slot)
        return kept

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
        self.display_surface.blit(panel, background_rect.topleft)
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
        self.display_surface.fill(accent, accent_edge)
        # Header row (bold).
        cursor_x = label_rect.left
        cursor_y = label_rect.top
        for surface in header:
            self.display_surface.blit(surface, (cursor_x, cursor_y))
            cursor_x += surface.get_width()
        cursor_y += row_height + LABEL_DIVIDER_TOP
        # Divider rule, inset by the card padding.
        rule_left = max(background_rect.left + LABEL_PAD_X, 0)
        rule_right = min(background_rect.right - LABEL_PAD_X, screen_width)
        if rule_right > rule_left:
            pygame.draw.line(
                self.display_surface,
                PANEL_BORDER,
                (rule_left, cursor_y),
                (rule_right, cursor_y),
                1,
            )
        cursor_y += 1 + LABEL_DIVIDER_BOTTOM
        for line in rows:
            cursor_x = label_rect.left
            for surface in line:
                self.display_surface.blit(surface, (cursor_x, cursor_y))
                cursor_x += surface.get_width()
            cursor_y += row_height + LABEL_LINE_GAP

    def draw_health_bars(
        self, entities: Iterable[pygame.sprite.Sprite], camera: Camera
    ) -> list[pygame.Rect]:
        """Draw the always-on HP bars; return the rects they occupy.

        The caller merges those rects into the frame's presentation set. A bar
        is not always inside its own sprite's dirty rect: it flips below the
        entity near the top of the screen, and its 30px minimum width is wider
        than a narrow sprite, so it can spill on every side.
        """
        drawn: list[pygame.Rect] = []
        for entity in entities:
            max_health = getattr(entity, "max_health", 0)
            if not max_health:
                continue

            health = getattr(entity, "health", 0)
            rect = getattr(entity, "hitbox", None) or getattr(entity, "rect", None)
            if rect is None or not camera.is_visible(rect):
                continue

            screen_rect = camera.apply(rect)
            background_rect = self._health_bar_rect(entity, screen_rect)
            if background_rect is None:
                continue
            drawn.append(background_rect)
            pygame.draw.rect(self.display_surface, (35, 37, 40), background_rect)
            health_ratio = max(0.0, min(1.0, health / max_health))
            health_width = background_rect.width * health_ratio
            color = (
                TEXT_OK if health_ratio > 0.5 else TEXT_WARN if health_ratio > 0.25 else TEXT_CRIT
            )
            if health_width > 0:
                pygame.draw.rect(
                    self.display_surface,
                    color,
                    (background_rect.x, background_rect.y, health_width, background_rect.height),
                )
            pygame.draw.rect(self.display_surface, PANEL_BORDER, background_rect, width=1)
        return drawn
