"""The overlay's dimensions, and the rule they are written in.

Extracted from `world_ui.py`, which was 2100 lines because the numbers lived
in the same file as the drawing. This checks the three things that make the
extraction safe: that every constant came across, that the facade no longer
re-exports them (so nothing quietly got a second copy), and the rule the tables
exist to enforce -- world units, scaled exactly once.
"""

import pytest

from src.ui import world_overlay_metrics as metrics_module
from src.ui import world_ui
from src.ui.world_overlay_metrics import WorldOverlayMetrics, scaled_world_px

#: Every name the module is meant to own. Written out rather than derived, so
#: that moving a constant *out* of it is a test failure and not a silent
#: re-export from somewhere else.
EXPECTED = {
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
    "WorldOverlayMetrics",
    "scaled_world_px",
}


def test_the_module_owns_exactly_the_named_dimensions() -> None:
    """`__all__` is the dimensions and the two things that build them.

    `MetricsCache` is in it because it is what keeps a stale table out of the
    three drawing layers, not because it is a dimension. The set is spelled out
    rather than derived, so a new constant that nobody re-exported fails here
    instead of quietly existing in one module only.
    """
    assert set(metrics_module.__all__) == EXPECTED | {"MetricsCache"}


def test_the_facade_does_not_re_export_the_dimensions() -> None:
    """The layers and `ui_manager` import from here, so a second name is a second number.

    `world_ui` used to re-export all 61 of them under `# noqa: F401`. Two had a
    caller in `src`; the rest were read by the test that asserted the re-export
    existed, which is the only thing that made them look used.

    The two it still needs are the ones it uses itself: ``OVERLAY_LAYERS`` to
    seed ``WorldUI.layers``, and ``WorldOverlayMetrics`` to annotate its own
    ``metrics`` property.
    """
    still_exported = EXPECTED & set(vars(world_ui))
    assert still_exported == {"OVERLAY_LAYERS", "WorldOverlayMetrics"}


def test_every_dimension_is_in_world_units_and_scales_once() -> None:
    """The rule the tables exist to enforce.

    These used to be handed straight to pygame while the rectangles they
    decorate came from `camera.apply`, which scales. At a density of 1.889
    every width and gap was 53% of its intent and the hitbox outlines were
    invisible -- an F1 toggle that drew nothing.
    """
    at_one = WorldOverlayMetrics(1.0)
    at_double = WorldOverlayMetrics(2.0)

    for name in dir(at_one):
        if name.startswith("_") or name == "scale":
            continue
        single = getattr(at_one, name)
        double = getattr(at_double, name)
        assert double == pytest.approx(single * 2), name


def test_a_dimension_never_rounds_away_to_nothing() -> None:
    """At a density below one a plain round gives 0, and a zero outline is a
    dimension that has stopped existing."""
    assert scaled_world_px(6.0, 0.01) == 1
    assert scaled_world_px(6.0, 0.0) == 1
    assert scaled_world_px(6.0, 1.0) == 6


def test_the_layer_names_are_the_ones_the_f_keys_toggle() -> None:
    assert metrics_module.OVERLAY_LAYERS == ("boxes", "labels", "velocities", "statics", "panels")


def test_the_hit_height_badges_are_compact() -> None:
    """Full names would cover the box they annotate.

    "high" abbreviates to "HIGH" and "overhead" to "OVH"; the point is the
    longest of them, not that every single one shrinks.
    """
    badges = metrics_module.HIT_HEIGHT_BADGES
    assert set(badges) == {"high", "mid", "low", "overhead"}
    assert badges["overhead"] == "OVH"
    assert max(len(badge) for badge in badges.values()) <= 4
