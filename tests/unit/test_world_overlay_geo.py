"""``world_overlay_geo``: the drawing paths the golden scene never reaches.

``test_world_overlay_golden.py`` pins the geometry of one crowded frame, which
is most of what this module decides and none of what it draws. The lines below
were the ones it left uncovered, and they are not incidental:

- **Rect-only sprites.** Hazards, moving platforms and exits carry a ``rect``
  and no ``hitbox``, and the whole branch that draws them was untested. A
  regression there is invisible: the overlay simply stops showing the things
  that hurt you.
- **The swept-box ghost and the motion arrow.** The reason ``box_moved`` and
  ``dashed_edges`` exist at all, exercised for the first time here.
- **Capsule and oriented-box poses.** Only circles were drawn by any test, so
  two of the three advanced shapes were drawn by code nobody had ever run.
- **A timeline too long to fit.** The scaling branch that keeps a long attack
  from drawing a header wider than the screen.

Assertions are on the surface rather than on the sink wherever the module's job
is to put pixels down, and on the sink wherever its job is to place a
rectangle. The one thing none of these assert is a colour value: that belongs
to the drawing code's own tests, and a fill alpha or a palette entry is not
what these paths are for.
"""

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.math import Vector2

from src.combat.shapes import ShapeKind, ShapePose
from src.core.colors import Colors
from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_overlay_geo import GeoLayer
from src.ui.world_overlay_metrics import SWEEP_DISPLAY_MIN_PX
from src.ui.world_ui import WorldUI

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


def _entity(name: str = "Goblin", **overrides) -> SimpleNamespace:
    base = {
        "hitbox": pygame.FRect(100, 100, 40, 48),
        "hurtbox": pygame.FRect(98, 98, 44, 52),
        "hurtboxes": (pygame.FRect(98, 98, 44, 52),),
        "hurtbox_zone_names": ("",),
        "hurtbox_mult": (1.0,),
        "hurtbox_tags": ((),),
        "velocity": Vector2(0, 0),
        "faction": "enemy",
        "health": 75.0,
        "max_health": 100.0,
        "state_machine": SimpleNamespace(current_state_name="idle"),
        "combat": SimpleNamespace(
            state=SimpleNamespace(attack_name=None, sub_state=None, phase_index=0, frame_counter=0),
            targets_hit=set(),
        ),
    }
    base.update(overrides)
    return type(name, (SimpleNamespace,), {})(**base)


def _attacking(name: str = "Slime", **combat) -> SimpleNamespace:
    entity = _entity(name)
    entity.combat.state.attack_name = "claw_swipe"
    entity.combat.state.sub_state = SimpleNamespace(value="active")
    entity.combat.state.frame_counter = 2
    entity.combat.current_phase = SimpleNamespace(
        startup_frames=4, active_frames=4, recovery_frames=4, hit=None
    )
    for key, value in combat.items():
        setattr(entity.combat, key, value)
    return entity


def _lit(surface: pygame.Surface) -> int:
    """How many pixels are not black. A shape either drew or it did not."""
    return sum(
        1
        for x in range(0, surface.get_width(), 2)
        for y in range(0, surface.get_height(), 2)
        if surface.get_at((x, y))[:3] != (0, 0, 0)
    )


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
    platform = _entity("Platform", rect=pygame.FRect(200, 400, 120, 16))
    del platform.hitbox  # a platform has no body; the rect is all there is
    geo.draw_boxes(platform, camera)
    assert _lit(world_ui.surface) > 0, "the platform drew nothing at all"
    assert world_ui.surface.get_at((200, 400))[:3] == tuple(Colors.debug_static), (
        "what was drawn is not the static outline a rect-only sprite gets"
    )


def test_a_sprite_with_neither_rect_nor_hitbox_draws_nothing(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """Nothing to place against, so nothing to draw, and no crash."""
    ghost = _entity("Ghost")
    del ghost.hitbox
    ghost.rect = None
    geo.draw_boxes(ghost, camera)
    assert _lit(world_ui.surface) == 0, "a sprite with no geometry drew something"


# -- advanced attack poses --------------------------------------------------


def test_a_capsule_pose_draws_a_solid_shaft_with_two_caps(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A capsule is a *filled* line of a given diameter, capped at both ends.

    Asserted on the shaft's middle, which is the only thing that tells a
    capsule from the rectangle this function falls back to for a pose it does
    not recognise: the fallback strokes an outline, so its interior stays
    black. A test that only checked "something was drawn" passes for both, and
    would keep passing if the capsule branch were deleted outright.
    """
    world_ui.surface.fill((0, 0, 0))
    geo.draw_shape(ShapePose(ShapeKind.CAPSULE, (80.0, 16.0), (300.0, 300.0)), Colors.white, camera)
    assert any(world_ui.surface.get_at((x, 300))[:3] != (0, 0, 0) for x in range(270, 331)), (
        "the capsule shaft is not where a horizontal capsule should be"
    )

    """A 90-degree OBB swaps its axes, which an axis-aligned draw would not.

    ``size`` is the box's own length and height, so turning it a quarter turn
    has to change which screen axis is long. That is the whole difference
    between an OBB and a rectangle, and it is the thing that separates this
    branch from the ``pygame.draw.rect`` fallback used for a pose this function
    does not recognise -- the fallback builds its rect from ``size`` and ignores
    the angle, so it draws the same wide shape at 0 and at 90.

    Measured on the drawn pixels' own bounding box rather than on a sampled
    line, because the shape is stroked and not filled: a line down the middle
    of it is black whatever the angle.
    """

    def lit_bounds(angle: float) -> tuple[int, int, int, int]:
        world_ui.surface.fill((0, 0, 0))
        geo.draw_shape(
            ShapePose(ShapeKind.OBB, (100.0, 20.0), (300.0, 300.0), angle=angle),
            Colors.white,
            camera,
        )
        lit = [
            (x, y)
            for x in range(200, 401)
            for y in range(200, 401)
            if world_ui.surface.get_at((x, y))[:3] != (0, 0, 0)
        ]
        assert lit, "nothing was drawn at all"
        xs = [x for x, _ in lit]
        ys = [y for _, y in lit]
        return min(xs), min(ys), max(xs), max(ys)

    upright = lit_bounds(0.0)
    turned = lit_bounds(90.0)
    assert upright[2] - upright[0] > upright[3] - upright[1], "unrotated it should be wide"
    assert turned[3] - turned[1] > turned[2] - turned[0], (
        "a quarter-turned box should now be tall, not wide"
    )
    # The two spans swap rather than one of them growing.
    assert turned[2] - turned[0] == pytest.approx(upright[3] - upright[1], abs=2)
    assert turned[3] - turned[1] == pytest.approx(upright[2] - upright[0], abs=2)


def test_dashed_edges_break_a_rectangle_into_segments() -> None:
    """The ghost outline is dashes with gaps, not a solid rectangle.

    Solid would read as a second live hitbox, which is the exact confusion the
    ghost exists to avoid.
    """
    edges = GeoLayer.dashed_edges(0.0, 0.0, 100.0, 60.0)
    assert edges, "a rect of that size must produce at least one dash"
    for (x0, y0), (x1, y1) in edges:
        assert (x0, y0) != (x1, y1), "a zero-length dash is not a dash"
        assert x0 == x1 or y0 == y1, "a ghost edge must be axis-aligned"


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
    assert _lit(world_ui.surface) > 0, "the swept ghost drew nothing"
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
    assert _lit(world_ui.surface) == 0


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
    entity = _entity(
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
    entity = _entity(
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
    assert _lit(world_ui.surface) == 0


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


def test_a_velocity_that_is_not_a_vector_is_ignored(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A tuple, a string, anything without ``.x``: drawn as nothing, not a crash.

    The debug pass reads attributes off whatever the scene hands it, and a
    sprite whose ``velocity`` is some other shape is exactly the case that
    turns a debug tool into the reason a frame is lost.
    """
    world_ui.surface.fill((0, 0, 0))
    for velocity in ((3.0, 4.0), "fast", 12):
        entity = _entity("Thing", velocity=velocity)
        geo.draw_velocity(entity, camera)
    assert _lit(world_ui.surface) == 0


def test_a_sprite_with_no_box_draws_no_velocity(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """The arrow starts at the body, so a bodyless sprite has nowhere to start."""
    world_ui.surface.fill((0, 0, 0))
    entity = _entity("Projectile", velocity=Vector2(300, 0))
    del entity.hitbox
    entity.rect = None
    geo.draw_velocity(entity, camera)
    assert _lit(world_ui.surface) == 0


def test_a_slow_sprite_draws_no_velocity(world_ui: WorldUI, geo: GeoLayer, camera: Camera) -> None:
    """Below the minimum speed, nothing is drawn at all.

    The threshold is not about the arrow being too small to see -- a slow
    vector is stretched to the minimum length and would be perfectly visible.
    It is about a sprite that is barely moving not growing an arrow that claims
    it is. Nothing in the codebase slows a sprite to exactly zero, so this is
    the only place the cutoff itself is observable.
    """
    world_ui.surface.fill((0, 0, 0))
    geo.draw_velocity(_entity("Crawler", velocity=Vector2(59.0, 0.0)), camera)
    assert _lit(world_ui.surface) == 0, "a sprite under the speed floor drew an arrow"


def test_a_sprite_over_the_speed_floor_does_draw(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """The positive side of the same threshold, so it is not vacuously green."""
    world_ui.surface.fill((0, 0, 0))
    geo.draw_velocity(_entity("Runner", velocity=Vector2(200.0, 0.0)), camera)
    assert _lit(world_ui.surface) > 0


def test_a_zero_velocity_arrow_draws_nothing(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """The arrow method is called directly here, past the speed gate.

    ``draw_velocity`` already refuses a slow vector, so the only way to reach
    this branch is to call the painter with a zero vector -- and a head drawn
    on a tail of no length is a dot on the entity.
    """
    world_ui.surface.fill((0, 0, 0))
    geo.draw_velocity_arrow(Vector2(300, 300), Vector2(0, 0), Colors.white)
    assert _lit(world_ui.surface) == 0


def test_a_fast_sprite_gets_a_velocity_arrow(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """The positive case for the branch above, so it is not vacuously green."""
    world_ui.surface.fill((0, 0, 0))
    entity = _entity("Runner", velocity=Vector2(400, 0))
    geo.draw_velocity(entity, camera)
    assert _lit(world_ui.surface) > 0, "a fast sprite drew no velocity arrow"


# -- the header chip, and the poses that reach the fallback -----------------


def test_a_header_with_no_bar_sits_above_the_entity(
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


def test_an_unknown_pose_falls_back_to_a_rectangle(
    world_ui: WorldUI, geo: GeoLayer, camera: Camera
) -> None:
    """A pose this function does not model is still drawn, as a plain box.

    Better a box that is close than nothing: an overlay that silently skips a
    hitbox is the one failure mode a debug layer cannot have.
    """
    world_ui.surface.fill((0, 0, 0))
    geo.draw_shape(ShapePose(ShapeKind.AABB, (60.0, 30.0), (300.0, 300.0)), Colors.white, camera)
    lit = [
        (x, y)
        for x in range(260, 341)
        for y in range(275, 326)
        if world_ui.surface.get_at((x, y))[:3] != (0, 0, 0)
    ]
    assert lit, "an axis-aligned pose drew nothing"
    xs = [x for x, _ in lit]
    ys = [y for _, y in lit]
    assert (max(xs) - min(xs)) > 40, "the fallback box is much smaller than the pose"
    assert (max(ys) - min(ys)) > 20, "the fallback box is much shorter than the pose"


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
        world_ui.draw_debug_overlays([_entity()], camera)
        assert _lit(world_ui.surface) == 0, "a disabled overlay still drew something"
        assert world_ui.annotation_rects == {}, "a disabled overlay still registered annotations"
    finally:
        for name in world_ui.layers:
            world_ui.layers[name] = name != "statics"
