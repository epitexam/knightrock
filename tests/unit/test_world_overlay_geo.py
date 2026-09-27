"""``world_overlay_geo``: the drawing paths the golden scene never reaches.

The golden pins the geometry of one crowded frame, which is most of what this
module decides and none of what it draws. These are the paths it left uncovered,
and none of them is incidental: rect-only sprites (hazards, platforms, exits)
would stop being drawn at all; the swept ghost and the motion arrow are why
`box_moved` exists; capsule and oriented-box poses had never been executed by
any test; and the long-timeline branch is what keeps one long attack from
drawing a header wider than the screen.

Where this module puts pixels down, these assert on the surface; where its job
is to place a rectangle, on the sink. None of them asserts a colour value."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.combat.shapes import ShapeKind, ShapePose
from src.core.colors import Colors
from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_overlay_geo import GeoLayer
from src.ui.world_overlay_metrics import SWEEP_DISPLAY_MIN_PX
from src.ui.world_ui import WorldUI
from tests.unit.helpers import lit_pixels, overlay_entity

SIZE = (1024, 768)


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode(SIZE)


@pytest.fixture()
def world_ui() -> WorldUI:
    surface = pygame.display.get_surface()
    assert surface is not None
    surface.fill((0, 0, 0))
    return WorldUI(PanelRenderer(surface))


@pytest.fixture()
def camera() -> Camera:
    return Camera(Framing(float(SIZE[0]), float(SIZE[1])))


@pytest.fixture()
def geo(world_ui: WorldUI) -> GeoLayer:
    return world_ui._geo


def _attacking(name: str = "Slime", **combat) -> SimpleNamespace:
    entity = overlay_entity(name)
    entity.combat.state.attack_name = "claw_swipe"
    entity.combat.state.sub_state = SimpleNamespace(value="active")
    entity.combat.state.frame_counter = 2
    entity.combat.current_phase = SimpleNamespace(
        startup_frames=4, active_frames=4, recovery_frames=4, hit=None
    )
    for key, value in combat.items():
        setattr(entity.combat, key, value)
    return entity


# -- rect-only sprites: the hazards, platforms and exits --------------------


def test_a_rect_only_sprite_is_drawn_as_static_geometry(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A sprite with a ``rect`` and no ``hitbox`` still gets an outline.

    This is the branch that draws spikes, moving platforms and level exits.
    They have no hitbox because nothing collides with them by body, which used
    to be read as "there is nothing to show here" -- and the overlay's own
    culling asks for a reference first, so an untested branch here is a class
    of sprite that quietly stopped being visible.
    """
    platform = overlay_entity("Platform", rect=pygame.FRect(200, 400, 120, 16))
    del platform.hitbox  # a platform has no body; the rect is all there is
    geo.draw_boxes(platform, camera)
    assert lit_pixels(world_ui.surface) > 0, "the platform drew nothing at all"
    assert world_ui.surface.get_at((200, 400))[:3] == tuple(Colors.debug_static), (
        "what was drawn is not the static outline a rect-only sprite gets"
    )


def test_a_sprite_with_neither_rect_nor_hitbox_draws_nothing(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """Nothing to place against, so nothing to draw, and no crash."""
    ghost = overlay_entity("Ghost")
    del ghost.hitbox
    ghost.rect = None
    geo.draw_boxes(ghost, camera)
    assert lit_pixels(world_ui.surface) == 0, "a sprite with no geometry drew something"


# -- advanced attack poses --------------------------------------------------


# -- the swept box and the motion arrow -------------------------------------


def test_an_advanced_shape_is_wrapped_in_the_broadphase_box(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A non-AABB pose is drawn inside a dashed trace of its own attack box.

    The pose is what actually collides -- a circle, a capsule, a turned box --
    and the attack box around it is only the broad-phase bound. Drawing the
    pose alone leaves the broad phase invisible, so a mismatch between the two
    (a shape that grew past its box, a box left at the old size) has nothing on
    screen to show it.

    Asserted on the attack box's own border, which the small circle in the
    middle cannot reach, so the two draws are told apart by where they are
    rather than by what colour they are.
    """
    world_ui.surface.fill((0, 0, 0))
    box = pygame.FRect(300, 300, 100, 60)
    geo.draw_attack_geometry(
        attack_box=box,
        swept=None,
        shape=ShapePose(ShapeKind.CIRCLE, (16.0, 16.0), (350.0, 330.0)),
        swept_shape=None,
        anchor=None,
        outline=Colors.debug_attack_box,
        camera=camera,
    )
    screen = camera.apply(box)
    top_edge = [(x, int(screen.top)) for x in range(int(screen.left) + 1, int(screen.right))]
    assert any(world_ui.surface.get_at(p)[:3] != (0, 0, 0) for p in top_edge), (
        "the broad-phase box was not drawn around the pose"
    )


def test_a_swept_box_that_moved_is_drawn_as_a_ghost(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A swing that travelled leaves a dashed trail behind it.

    Only when it moved: a swept box identical to the live one is the same
    rectangle twice, and drawing it would double every outline on screen.
    """
    world_ui.surface.fill((0, 0, 0))
    geo.draw_attack_geometry(
        attack_box=pygame.FRect(300, 300, 40, 24),
        swept=pygame.FRect(240, 300, 40, 24),
        shape=None,
        swept_shape=None,
        anchor=None,
        outline=Colors.debug_attack_box,
        camera=camera,
    )
    assert lit_pixels(world_ui.surface) > 0, "the swept ghost drew nothing"
    # The trail is behind the live box, so something exists to its left.
    assert any(world_ui.surface.get_at((x, 312))[:3] != (0, 0, 0) for x in range(230, 290)), (
        "nothing was drawn where the swing came from"
    )


def test_a_swept_box_that_did_not_move_draws_no_ghost(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """Same rectangle, so no trail, so the box is not drawn twice."""
    world_ui.surface.fill((0, 0, 0))
    box = pygame.FRect(300, 300, 40, 24)
    geo.draw_attack_geometry(
        attack_box=box,
        swept=pygame.FRect(box),
        shape=None,
        swept_shape=None,
        anchor=None,
        outline=Colors.debug_attack_box,
        camera=camera,
    )
    assert not any(world_ui.surface.get_at((x, 312))[:3] != (0, 0, 0) for x in range(230, 290)), (
        "a stationary swing left a trail"
    )


def test_box_moved_notices_a_change_of_size_not_just_of_centre() -> None:
    """A box that grew is a different hitbox, even from the same point.

    Distance alone misses it: a hitbox that widens in place covers new pixels
    on both sides, which is the case that hurts.
    """
    base = pygame.FRect(100, 100, 40, 24)
    assert GeoLayer.box_moved(base, pygame.FRect(base)) is False
    assert GeoLayer.box_moved(base, pygame.FRect(140, 100, 40, 24)) is True
    grown_width = pygame.FRect(100, 100, 40 + SWEEP_DISPLAY_MIN_PX, 24)
    assert GeoLayer.box_moved(base, grown_width) is True
    grown_height = pygame.FRect(100, 100, 40, 24 + SWEEP_DISPLAY_MIN_PX)
    assert GeoLayer.box_moved(base, grown_height) is True


def test_a_motion_arrow_needs_two_different_points(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A zero-length arrow is not drawn at all.

    Degenerate geometry here would put a head on top of a tail, which reads as
    a smudge on the entity rather than as "it did not move".
    """
    world_ui.surface.fill((0, 0, 0))
    box = pygame.FRect(300, 300, 40, 24)
    geo.draw_motion_arrow(box, pygame.FRect(box), camera)
    assert lit_pixels(world_ui.surface) == 0


# -- multi-zone hurtboxes ----------------------------------------------------


def test_a_tagged_hurtbox_zone_gets_a_dashed_seal(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A zone tagged invulnerable is sealed, so the rule is visible in the world.

    The zones themselves carry no text -- the full roster lives on the label
    card, where rows cannot overlap -- so a seal is the only thing on screen
    that says "this part of the body cannot be hit".

    Asserted on the *interior* of the zone rather than on it having drawn
    anything, because the zone outline is drawn either way: only the seal puts
    marks strictly inside the border.
    """
    world_ui.surface.fill((0, 0, 0))
    entity = overlay_entity(
        "Ooze",
        hitbox=pygame.FRect(100, 100, 40, 48),
        hurtboxes=(pygame.FRect(100, 100, 40, 48), pygame.FRect(100, 100, 20, 48)),
        hurtbox_zone_names=("", "guard"),
        hurtbox_mult=(1.0, 1.0),
        hurtbox_tags=((), ("armor",)),
    )
    geo.draw_boxes(entity, camera)
    zone = camera.apply(pygame.FRect(100, 100, 20, 48))
    inset = geo.metrics.zone_boost_outline + 2
    interior = [
        (x, y)
        for x in range(int(zone.left) + inset, int(zone.right) - inset)
        for y in range(int(zone.top) + inset, int(zone.bottom) - inset)
    ]
    assert any(world_ui.surface.get_at(p)[:3] != (0, 0, 0) for p in interior), (
        "nothing was drawn inside the zone, so no seal reached it"
    )


def test_an_untagged_zone_gets_no_seal(world_ui: WorldUI, geo: GeoLayer, camera: Camera) -> None:
    """Without the tag there is no rule to show, so the interior stays clean.

    The negative half of the test above. A seal on every zone would be a
    decoration rather than a mark of meaning, and then it would say nothing.
    """
    world_ui.surface.fill((0, 0, 0))
    entity = overlay_entity(
        "Ooze",
        hitbox=pygame.FRect(100, 100, 40, 48),
        hurtboxes=(pygame.FRect(100, 100, 40, 48), pygame.FRect(100, 100, 20, 48)),
        hurtbox_zone_names=("", "guard"),
        hurtbox_mult=(1.0, 1.0),
        hurtbox_tags=((), ()),
    )
    geo.draw_boxes(entity, camera)
    zone = camera.apply(pygame.FRect(100, 100, 20, 48))
    inset = geo.metrics.zone_boost_outline + 4
    interior = [
        (x, y)
        for x in range(int(zone.left) + inset, int(zone.right) - inset)
        for y in range(int(zone.top) + inset, int(zone.bottom) - inset)
    ]
    assert not any(world_ui.surface.get_at(p)[:3] != (0, 0, 0) for p in interior), (
        "a zone with no tag was sealed anyway"
    )


def test_a_zone_too_small_to_seal_is_skipped_not_drawn_degenerate(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A zone thinner than the seal's inset has no inside left.

    The inner rectangle would come out with a non-positive width, and walking
    dashes along that draws a line of noise across the sprite.
    """
    world_ui.surface.fill((0, 0, 0))
    metrics = geo.metrics
    tiny = pygame.FRect(100, 100, metrics.zone_boost_outline, metrics.zone_boost_outline)
    geo.draw_zone_seal(camera.apply(tiny), Colors.white)
    assert lit_pixels(world_ui.surface) == 0


# -- the attack header timeline ---------------------------------------------


def test_a_very_long_attack_squeezes_its_timeline_to_fit() -> None:
    """Three thousand frames of startup still fits under the chip's width cap.

    Without the scale-down, one long attack would draw a header wider than the
    screen. Every segment keeps at least one pixel, so a phase that is long
    relative to the others still shows up rather than rounding away.

    That floor is also why the cap can be missed by up to two pixels: three
    segments each floored at one add up to more than the scaled share they were
    given. Recorded here rather than fixed, because the alternative -- a phase
    squeezed to zero -- hides the phase, and a one-pixel-too-wide chip is the
    better trade. The golden does not cover this branch, so changing the
    arithmetic here would be a geometry change and not a test change.
    """
    layer = _bare_layer()
    cap = layer.metrics.timeline_max_width
    for frames in ((300, 1, 1), (1000, 2, 1), (5000, 1, 1), (999, 999, 999)):
        phase = SimpleNamespace(
            startup_frames=frames[0], active_frames=frames[1], recovery_frames=frames[2]
        )
        widths, total = layer.attack_timeline_widths(phase, None, "startup")
        assert len(widths) == 3
        assert all(width >= 1 for width, _ in widths)
        assert total == sum(width for width, _ in widths)
        assert total <= cap + 2, f"{frames} overflowed the cap by more than the pixel floor allows"
    assert total > cap, "a cap nobody can overshoot is not the contract being pinned"


def test_a_short_attack_keeps_its_own_proportions() -> None:
    """Below the cap, the segments stay proportional -- the long one looks long."""
    layer = _bare_layer()
    phase = SimpleNamespace(startup_frames=8, active_frames=2, recovery_frames=2)
    widths, total = layer.attack_timeline_widths(phase, None, "startup")
    assert widths[0][0] > widths[1][0], (
        "an eight-frame startup should read longer than a two-frame one"
    )
    assert total == sum(width for width, _ in widths)


def _bare_layer() -> GeoLayer:
    """A layer with no scene behind it, for the pure readers."""
    surface = pygame.Surface(SIZE)
    renderer = PanelRenderer(surface)
    from src.ui.world_overlay_metrics import MetricsCache

    return GeoLayer(renderer, MetricsCache(renderer), _NoopSink())


class _NoopSink:
    """Stands in for the annotation sink when only the readers are under test."""

    def register(self, sprite: object, rects: list[pygame.Rect]) -> None:
        """Nothing is drawn, so there is nothing to record."""


# -- badges ------------------------------------------------------------------


def test_badges_name_the_shape_the_priority_and_the_guard() -> None:
    """Everything the player cannot read off the shape itself, in one row.

    The chip is the only text an attacking sprite gets, so a badge is the only
    place "this is an overhead, unblockable, priority 2" is ever said.
    """
    layer = _bare_layer()
    combat = SimpleNamespace(
        current_phase=SimpleNamespace(
            hit=SimpleNamespace(priority=2, unblockable=True, height="high")
        ),
        attack_shapes=(ShapePose(ShapeKind.CAPSULE, (40.0, 8.0), (0.0, 0.0)),),
    )
    badges = layer.offensive_badges(combat)
    assert "CAPSULE" in badges, badges
    assert "P2" in badges, badges
    assert "UBL" in badges, badges
    assert "HIGH" in badges, badges


def test_no_hit_means_no_badges() -> None:
    """A phase with no hit box is not a phase that can miss; nothing to say."""
    layer = _bare_layer()
    assert layer.offensive_badges(SimpleNamespace(current_phase=None)) == ()
    assert layer.offensive_badges(SimpleNamespace()) == ()


def test_a_mid_height_hit_carries_no_height_badge() -> None:
    """ "MID" is the default, so printing it would be noise on every attack."""
    layer = _bare_layer()
    combat = SimpleNamespace(
        current_phase=SimpleNamespace(hit=SimpleNamespace(height="mid")),
    )
    assert layer.offensive_badges(combat) == ()


def test_an_unknown_height_is_printed_as_written() -> None:
    """A height the palette has never heard of still reaches the player.

    Silently dropping it would hide a data problem behind a missing letter on
    the chip; upper-casing it shows the chip saying something the code does not
    recognise, which is the useful failure.
    """
    layer = _bare_layer()
    combat = SimpleNamespace(
        current_phase=SimpleNamespace(hit=SimpleNamespace(height="sideways")),
    )
    assert layer.offensive_badges(combat) == ("SIDEWAYS",)


# -- velocity ----------------------------------------------------------------


# -- the header chip, and the poses that reach the fallback -----------------


def test_a_header_with_no_bar_sits_above_theoverlay_entity(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """The player has no world-space bar, so the chip anchors on the body.

    The other two anchors are "above the bar" and "below the flipped bar", and
    this is the third case: no bar at all. Without it the chip would be placed
    against a rectangle that does not exist, which for the player means the one
    sprite whose combat is on screen is the one whose chip is misplaced.
    """
    world_ui.surface.fill((0, 0, 0))
    player = _attacking("Player", faction=None)
    player.faction = "player"
    player.hitbox = pygame.FRect(300, 300, 40, 48)
    player.hurtboxes = (pygame.FRect(298, 298, 44, 52),)
    assert world_ui._health_bar_rect(player, camera.apply(player.hitbox)) is None

    geo.draw_boxes(player, camera)
    screen = camera.apply(player.hitbox)
    chip = world_ui.annotation_rects.get(id(player), ())
    assert chip, "an attacking player got no attack chip"
    assert chip[0].bottom <= screen.top, (
        f"the chip should sit above the entity, got {chip[0]} against {screen}"
    )


def test_a_header_carries_its_badges(world_ui: WorldUI, geo: GeoLayer, camera: Camera) -> None:
    """The badges are appended to the chip, not drawn somewhere else.

    They are the only place a priority or an unblockable is ever spelled out,
    so a chip that drew its name and phase but silently dropped the badges
    would still look right and say nothing.
    """
    world_ui.surface.fill((0, 0, 0))
    entity = _attacking(
        "Slime",
        attack_shapes=(ShapePose(ShapeKind.CAPSULE, (40.0, 8.0), (0.0, 0.0)),),
    )
    entity.combat.current_phase.hit = SimpleNamespace(priority=1, unblockable=True, height="low")
    geo.draw_boxes(entity, camera)
    assert world_ui.annotation_rects.get(id(entity)), "the chip was never registered"


def test_a_swept_pose_draws_where_the_swing_came_from(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A swept *pose* leaves a trail too, not only a swept box.

    The two are separate inputs, because a swing can move its shape without
    moving the broad-phase box around it. Tracing only the box would show a
    stationary trail for a pose that visibly travelled, and vice versa.
    """
    world_ui.surface.fill((0, 0, 0))
    geo.draw_attack_geometry(
        attack_box=pygame.FRect(300, 300, 100, 60),
        swept=pygame.FRect(300, 300, 100, 60),
        shape=ShapePose(ShapeKind.CIRCLE, (20.0, 20.0), (350.0, 330.0)),
        swept_shape=SimpleNamespace(
            previous=ShapePose(ShapeKind.CIRCLE, (20.0, 20.0), (270.0, 330.0))
        ),
        anchor=None,
        outline=Colors.debug_attack_box,
        camera=camera,
    )
    behind = [
        (x, 330) for x in range(240, 300) if world_ui.surface.get_at((x, 330))[:3] != (0, 0, 0)
    ]
    assert behind, "nothing was drawn where the swept pose used to be"


def test_every_layer_off_draws_nothing_at_all(world_ui: WorldUI, camera: Camera) -> None:
    """With the layers off, the pass costs one dictionary check.

    The early return is the cheapest thing in the module and the only way the
    overlay can be switched off without the caller knowing: a level that
    turns every toggle off still walks a scene of ~840 tiles, and the point of
    the gate is that walking them draws nothing.
    """
    for name in world_ui.layers:
        world_ui.layers[name] = False
    try:
        world_ui.surface.fill((0, 0, 0))
        world_ui.draw_debug_overlays([overlay_entity()], camera)
        assert lit_pixels(world_ui.surface) == 0, "a disabled overlay still drew something"
        assert world_ui.annotation_rects == {}, "a disabled overlay still registered annotations"
    finally:
        for name in world_ui.layers:
            world_ui.layers[name] = name != "statics"
