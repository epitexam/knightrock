"""``world_overlay_shapes``: the three advanced poses, and the dashed outline.

Extracted from ``tests/unit/test_world_overlay_geo.py`` when the module it
tests was split out, so the tests moved with the code rather than reaching
across into a module that no longer owns it.
"""

import os

import pygame
import pytest

from src.combat.shapes import ShapeKind, ShapePose
from src.core.colors import Colors
from src.core.display.framing import Framing
from src.core.rendering.camera import Camera
from src.ui.panel_renderer import PanelRenderer
from src.ui.world_overlay_shapes import ShapeLayer, dashed_edges
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
def shapes(world_ui: WorldUI) -> ShapeLayer:
    return world_ui._geo.shapes


def test_a_capsule_pose_draws_a_solid_shaft_with_two_caps(
    world_ui: WorldUI, shapes: ShapeLayer, camera: Camera
) -> None:
    """A capsule is a *filled* line of a given diameter, capped at both ends.

    Asserted on the shaft's middle, which is the only thing that tells a
    capsule from the rectangle this function falls back to for a pose it does
    not recognise: the fallback strokes an outline, so its interior stays
    black. A test that only checked "something was drawn" passes for both, and
    would keep passing if the capsule branch were deleted outright.
    """
    world_ui.surface.fill((0, 0, 0))
    shapes.draw_shape(
        ShapePose(ShapeKind.CAPSULE, (80.0, 16.0), (300.0, 300.0)), Colors.white, camera
    )
    assert any(world_ui.surface.get_at((x, 300))[:3] != (0, 0, 0) for x in range(270, 331)), (
        "the capsule shaft is not where a horizontal capsule should be"
    )


def test_an_oriented_box_is_rotated_not_just_resized(
    world_ui: WorldUI, shapes: ShapeLayer, camera: Camera
) -> None:
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
        shapes.draw_shape(
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
    edges = dashed_edges(0.0, 0.0, 100.0, 60.0)
    assert edges, "a rect of that size must produce at least one dash"
    for (x0, y0), (x1, y1) in edges:
        assert (x0, y0) != (x1, y1), "a zero-length dash is not a dash"
        assert x0 == x1 or y0 == y1, "a ghost edge must be axis-aligned"


def test_an_unknown_pose_falls_back_to_a_rectangle(
    world_ui: WorldUI, shapes: ShapeLayer, camera: Camera
) -> None:
    """A pose this function does not model is still drawn, as a plain box.

    Better a box that is close than nothing: an overlay that silently skips a
    hitbox is the one failure mode a debug layer cannot have.
    """
    world_ui.surface.fill((0, 0, 0))
    shapes.draw_shape(ShapePose(ShapeKind.AABB, (60.0, 30.0), (300.0, 300.0)), Colors.white, camera)
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
