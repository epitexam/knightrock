"""Every dimension the world-space overlay draws with, in one place.

Extracted from ``world_ui.py``, which was 2100 lines because the *numbers*
lived in the same file as the *drawing*. That is the worst of both: a
constant that only matters to the label placer is invisible when you are
looking at the box drawer, and the drawing code is buried under four
hundred lines of geometry tables that no reader of it needs to see.

**World units, always.** Every constant here is a dimension in world units
and is multiplied by the target's pixel density exactly once, by
:class:`WorldOverlayMetrics`. The reason that rule exists is a bug worth
recording: these used to be module constants handed straight to pygame while
the rectangles they decorate came from ``camera.apply``, which scales. At a
density of 1.889 every width, padding and gap was 53% of its intent and the
hitbox outlines were invisible -- an F1 toggle that drew nothing, which is
indistinguishable from a broken one.

So the tables are grouped by what they size, each with the reason it has the
value it has, and nothing here is a bare number.
"""

from dataclasses import dataclass

from src.core.colors import Color, Colors
from src.ui.styles import TEXT_MUTED

__all__ = [
    "ANNOTATION_CHIP_FILL",
    "ANNOTATION_CHIP_PAD",
    "ANNOTATION_MAX_DODGES",
    "ANNOTATION_TIER_GAP",
    "ATTACK_HEADER_RULE_GAP",
    "ATTACK_HEADER_TEXT_GAP",
    "BOX_DOT_CORE_RADIUS",
    "BOX_DOT_INSET",
    "BOX_DOT_RADIUS",
    "BOX_DOT_RIM",
    "BOX_DOT_RIM_WIDTH",
    "CLASH_MARKER_LIFETIME",
    "CLASH_MARKER_RADIUS",
    "CLASH_TICK_S",
    "COMBAT_PANEL_TITLE",
    "HEALTH_BAR_ANCHOR_GAP",
    "HEALTH_BAR_HEIGHT",
    "HEALTH_BAR_LABEL_GAP",
    "HIT_HEIGHT_BADGES",
    "LABEL_ANCHOR_GAP",
    "LABEL_BAR_CLEARANCE",
    "LABEL_DIVIDER_BOTTOM",
    "LABEL_DIVIDER_TOP",
    "LABEL_LINE_GAP",
    "LABEL_MAX_NUDGES",
    "LABEL_NUDGE_PX",
    "LABEL_PAD_X",
    "LABEL_PAD_Y",
    "LABEL_SEP",
    "LABEL_TAG",
    "METRICS_TICK_DIVISOR",
    "OVERLAY_LAYERS",
    "PHASE_OUTLINE_COLORS",
    "SWEEP_ARROW_HEAD",
    "SWEEP_DISPLAY_MIN_PX",
    "SWEEP_GHOST_WIDTH",
    "TIMELINE_BAR_HEIGHT",
    "TIMELINE_MAX_WIDTH",
    "TIMELINE_PX_PER_FRAME",
    "VELOCITY_HEAD_MAX",
    "VELOCITY_HEAD_MIN",
    "VELOCITY_HEAD_RATIO",
    "VELOCITY_HEAD_WIDTH_CAP",
    "VELOCITY_HEAD_WIDTH_RATIO",
    "VELOCITY_MIN_LENGTH",
    "VELOCITY_MIN_SPEED",
    "VELOCITY_NECK_WIDTH",
    "VELOCITY_OUTLINE",
    "VELOCITY_OUTLINE_WIDTH",
    "VELOCITY_PREVIEW_S",
    "VELOCITY_TAIL_RADIUS",
    "VELOCITY_TAIL_WIDTH",
    "ZONE_BOOST_OUTLINE_WIDTH",
    "ZONE_FILL_ALPHA",
    "ZONE_OUTLINE_WIDTH",
    "ZONE_SEAL_DASH",
    "ZONE_SEAL_GAP",
    "ZONE_SEAL_WIDTH",
    "MetricsCache",
    "WorldOverlayMetrics",
    "scaled_world_px",
]


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


@dataclass(frozen=True)
class WorldOverlayMetrics:
    """Every overlay dimension, in target pixels, for one pixel density.

    One table for fourteen numbers, and the reason is a bug: they used to be
    module constants handed straight to pygame while the *rectangles* they
    decorate came from ``camera.apply``, which scales. The two were in different
    units, so at a density of 1.889 every width, padding and gap was 53% of its
    intent and the hitbox outlines were invisible. Writing them down once, in
    world units, and multiplying here is the only way they cannot drift apart
    again -- and it costs fourteen multiplications per frame.
    """

    scale: float

    @property
    def zone_outline(self) -> int:
        return scaled_world_px(ZONE_OUTLINE_WIDTH, self.scale)

    @property
    def zone_boost_outline(self) -> int:
        return scaled_world_px(ZONE_BOOST_OUTLINE_WIDTH, self.scale)

    @property
    def seal_dash(self) -> int:
        return scaled_world_px(ZONE_SEAL_DASH, self.scale)

    @property
    def seal_gap(self) -> int:
        return scaled_world_px(ZONE_SEAL_GAP, self.scale)

    @property
    def seal_width(self) -> int:
        return scaled_world_px(ZONE_SEAL_WIDTH, self.scale)

    @property
    def tier_gap(self) -> int:
        return scaled_world_px(ANNOTATION_TIER_GAP, self.scale)

    @property
    def chip_pad(self) -> int:
        return scaled_world_px(ANNOTATION_CHIP_PAD, self.scale)

    @property
    def clash_radius(self) -> int:
        return scaled_world_px(CLASH_MARKER_RADIUS, self.scale)

    @property
    def timeline_bar_height(self) -> int:
        return scaled_world_px(TIMELINE_BAR_HEIGHT, self.scale)

    @property
    def timeline_px_per_frame(self) -> int:
        return scaled_world_px(TIMELINE_PX_PER_FRAME, self.scale)

    @property
    def timeline_max_width(self) -> int:
        return scaled_world_px(TIMELINE_MAX_WIDTH, self.scale)

    @property
    def header_text_gap(self) -> int:
        return scaled_world_px(ATTACK_HEADER_TEXT_GAP, self.scale)

    @property
    def header_rule_gap(self) -> int:
        return scaled_world_px(ATTACK_HEADER_RULE_GAP, self.scale)

    @property
    def label_pad_x(self) -> int:
        return scaled_world_px(LABEL_PAD_X, self.scale)

    @property
    def label_pad_y(self) -> int:
        return scaled_world_px(LABEL_PAD_Y, self.scale)

    @property
    def label_line_gap(self) -> int:
        return scaled_world_px(LABEL_LINE_GAP, self.scale)

    @property
    def label_divider_top(self) -> int:
        return scaled_world_px(LABEL_DIVIDER_TOP, self.scale)

    @property
    def label_divider_bottom(self) -> int:
        return scaled_world_px(LABEL_DIVIDER_BOTTOM, self.scale)

    @property
    def label_nudge(self) -> int:
        return scaled_world_px(LABEL_NUDGE_PX, self.scale)

    @property
    def label_bar_clearance(self) -> int:
        return scaled_world_px(LABEL_BAR_CLEARANCE, self.scale)

    @property
    def label_anchor_gap(self) -> int:
        return scaled_world_px(LABEL_ANCHOR_GAP, self.scale)


def scaled_world_px(world_px: float, scale: float) -> int:
    """A world dimension in whole target pixels, never below one.

    The floor is not a nicety: at a density below one -- a window smaller than
    the framing -- a plain round gives 0, and a *zero* outline or padding is a
    dimension that has stopped existing.
    """
    return max(1, round(world_px * scale))


class MetricsCache:
    """The one place that knows when the metrics table is stale.

    The table is fourteen numbers, and rebuilding it means fourteen
    multiplications. On a static window that is pure waste, so it is cached and
    keyed on the render scale -- one identity comparison per read, and a full
    rebuild on a resize.

    It lives here, as its own object, because three layers now draw with these
    numbers and the earlier arrangement made them reach it through a callable:
    ``WorldUI.metrics`` is a property, so each layer held a lambda wrapping it,
    and a draw pass reads ``metrics`` several times per sprite. Measured on a
    96-entity frame, that one extra frame per read cost about 7 % of the whole
    overlay pass. Passing the cache itself turns each read into one attribute
    access and keeps the rebuild rule in exactly one place -- which is also the
    only way the three layers cannot disagree about when the table went stale.
    """

    def __init__(self, renderer: object) -> None:
        self._renderer = renderer
        self._scale: float = -1.0
        self._table = WorldOverlayMetrics(1.0)

    @property
    def current(self) -> WorldOverlayMetrics:
        """The table for the density in force right now."""
        scale = self._renderer.world_scale  # type: ignore[attr-defined]
        if scale != self._scale:
            self._scale = scale
            self._table = WorldOverlayMetrics(scale)
        return self._table
