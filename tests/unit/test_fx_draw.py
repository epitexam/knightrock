"""The FX drawing primitives: whole pixels, symmetry, and a stepped fade.

The whole game is magnified with nearest-neighbour scaling, so a primitive
that returns half-pixels or a continuous alpha ramp is not a small imprecision
here: it is a different look from the rest of the game. These tests pin the
three rules every shape in `src/core/fx/draw.py` rests on.
"""

import math
import os

import pygame
import pytest

from src.core.fx import draw


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


def blank(size: tuple[int, int]) -> pygame.Surface:
    return pygame.Surface(size, pygame.SRCALPHA)


def test_snap_rounds_half_up_to_whole_pixels() -> None:
    assert draw.snap(0.4) == 0
    assert draw.snap(0.5) == 1
    assert draw.snap(-0.5) == 0
    assert draw.snap(2.49) == 2


def test_a_disc_lands_only_on_whole_pixels() -> None:
    surface = blank((17, 17))
    draw.disc(surface, (255, 255, 255), (8.4, 7.6), 5.2)

    xs = [x for x in range(17) for y in range(17) if surface.get_at((x, y))[3]]
    ys = [y for x in range(17) for y in range(17) if surface.get_at((x, y))[3]]
    assert (min(xs), max(xs)) == (3, 12), "radius 5, snapped, about the rounded centre"
    assert (min(ys), max(ys)) == (3, 12)


def test_a_ring_has_a_hole_punched_through_it() -> None:
    surface = blank((21, 21))
    draw.ring(surface, (255, 255, 255), (10, 10), 9, 2)

    assert surface.get_at((10, 10))[3] == 0, "the centre has to be transparent"
    assert surface.get_at((10, 1))[3] == 255, "and the rim has to be solid"


def test_an_ellipse_ring_is_flat() -> None:
    surface = blank((41, 21))
    draw.ellipse_ring(surface, (255, 255, 255), (20, 10), 18, 6, 2)

    lit = [(x, y) for x in range(41) for y in range(21) if surface.get_at((x, y))[3]]
    assert max(x for x, _ in lit) - min(x for x, _ in lit) > 2 * (
        max(y for _, y in lit) - min(y for _, y in lit)
    )


def test_lobes_union_into_one_silhouette_rather_than_a_pile() -> None:
    """The lobes are one shape, so the ink rim has to follow the outside only.

    This is the property that makes a cloud out of several discs. Drawn one at
    a time with a rim each, the interior boundaries would be inked too and the
    shape would come out looking like a stack of coins; drawn as a single
    shape, the rim is the outline of the union and the middle is solid.
    """
    surface = blank((41, 41))
    lobes = ((0.0, 0.0, 8.0), (-7.0, 2.0, 5.0), (6.0, -1.0, 4.0))
    draw.ink_shape(surface, draw.lobe_shape((20, 20), lobes), (255, 255, 255), (0, 0, 0), 1)

    assert surface.get_at((20, 20))[:3] == (255, 255, 255), "the middle is body, not a seam"
    assert surface.get_at((0, 0))[3] == 0, "and nothing is drawn where no lobe reaches"
    lit = [(x, y) for x in range(41) for y in range(41) if surface.get_at((x, y))[3]]
    xs = [x for x, _ in lit]
    ys = [y for _, y in lit]
    # Lumpy: the satellites have to push the outline out past the central disc.
    assert max(xs) - min(xs) > 16 and max(ys) - min(ys) > 16


def test_a_star_is_symmetric_about_its_heading() -> None:
    """A sparkle with four points has to have the same four arms.

    Snapping each vertex on its own can leave a star a pixel lopsided, which
    is exactly the kind of thing that reads as a hand-placed mistake.
    """
    points = draw.star_points((12, 12), 9, 3, 4, heading=0.0)

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    assert min(xs) == 24 - max(xs), "left and right arms must match"
    assert min(ys) == 24 - max(ys), "top and bottom arms must match"
    assert len(set(points)) == 8


def test_a_star_heading_aims_its_first_point() -> None:
    right = draw.star_points((20, 20), 9, 3, 4, heading=0.0)
    left = draw.star_points((20, 20), 9, 3, 4, heading=math.pi)

    assert max(point[0] for point in right) > 20
    assert min(point[0] for point in left) < 20


def test_a_streak_tapers_to_its_tip() -> None:
    points = draw.streak_points((0, 0), 24, 6, 0.0)
    xs = [point[0] for point in points]

    def thickness_at(x: int) -> int:
        rows = [point[1] for point in points if point[0] == x]
        return max(rows) - min(rows)

    assert min(xs) == -24, "the tip sits a full length back from the anchor"
    assert thickness_at(0) == 6, "the anchor end is the full width"
    assert thickness_at(0) > thickness_at(-15), "and it narrows along the way"
    assert thickness_at(-24) == 0, "down to a point at the tip"


def test_an_inked_polygon_is_cut_to_fit_and_keeps_a_rim() -> None:
    surface = draw.inked_polygon(
        draw.streak_points((0, 0), 20, 6, 0.0), (200, 220, 255), (20, 40, 80), 1
    )

    width, height = surface.get_size()
    edges = [surface.get_at((x, y))[3] for x in range(width) for y in (0, height - 1)]
    edges += [surface.get_at((x, y))[3] for y in range(height) for x in (0, width - 1)]
    assert set(edges) == {0}, "a pixel of spare all round, and no more"
    colours = {
        tuple(surface.get_at((x, y)))[:3]
        for x in range(surface.get_width())
        for y in range(surface.get_height())
    }
    assert (20, 40, 80) in colours, "the ink pass must be visible"
    assert (200, 220, 255) in colours, "and the fill must be too"


def test_the_ink_rim_grows_a_shape_outward_and_never_shrinks_it() -> None:
    """The mitre offset, not a scale about the centre.

    Scaling about the centre cannot lengthen a tapered line without also
    fattening its middle, and it turned every speed line into a lozenge.
    """
    body = draw.streak_points((0, 0), 20, 4, 0.0)
    grown = draw._offset_polygon(body, 1.0)

    assert len(grown) == len(body)
    assert max(point[1] for point in grown) > max(point[1] for point in body)
    assert min(point[1] for point in grown) < min(point[1] for point in body)
    assert all(
        draw.snap(point[0]) == point[0] and draw.snap(point[1]) == point[1] for point in grown
    )


def test_polygon_bounds_leaves_a_pixel_of_spare() -> None:
    left, top, width, height = draw.polygon_bounds([(4, 6), (10, 6), (10, 12)])

    assert (left, top) == (3, 5)
    assert (width, height) == (9, 9)


def test_the_fade_ramps_up_then_falls_in_discrete_steps() -> None:
    """Discrete levels, and a fade-in, or a particle pops into existence.

    A continuous ramp turns into a field of half-transparent pixels once the
    surface is magnified with nearest neighbour, which reads as dirt.
    """
    levels = [draw.life_level(life / 20.0, 0.2) for life in range(21)]

    assert levels[0] == 0, "a new particle is invisible"
    assert levels[3] > levels[0], "it has to ramp up over the fade-in"
    assert levels[4] == draw.ALPHA_STEPS - 1, "and be at full brightness by its end"
    assert levels[10] < draw.ALPHA_STEPS - 1, "then fall away"
    assert levels[-1] == 0, "and be gone by the end"
    assert set(levels).issubset(range(draw.ALPHA_STEPS))


def test_alpha_of_a_level_is_a_whole_number_of_steps() -> None:
    assert draw.alpha_of_level(0) == 0
    assert draw.alpha_of_level(draw.ALPHA_STEPS - 1) == 255
    assert draw.life_alpha(0.5, 0.0) == draw.alpha_of_level(draw.life_level(0.5, 0.0))


def test_an_opening_shape_starts_at_its_smallest_step_and_grows() -> None:
    """`spread_step` is not a fade, and the shatter arc depends on the difference.

    `life_level` falls from full brightness, so indexing it with a growing
    shape would show the widest frame first and shrink from there -- a guard
    failing by inflating instead of coming apart. This is the curve the
    broken ring rides, and it had no test at all.
    """
    steps = [draw.spread_step(index / 8.0, 5) for index in range(9)]

    assert steps[0] == 0, "it starts closed"
    assert steps == sorted(steps), "and only ever opens"
    assert steps[-1] == 4, "reaching the widest frame by the end"
    assert len(set(steps)) > 1, "a shape that never changes is not opening"


def test_opening_outlives_the_fraction_it_was_given() -> None:
    """Past `opened_by` the shape is as open as it gets, not off the ladder.

    The shatter arc holds its last frame for the rest of its life, so a
    curve that kept climbing would index past the ladder and raise.
    """
    assert draw.spread_step(1.0, 4, opened_by=0.3) == 3
    assert draw.spread_step(1.0, 4, opened_by=0.3) == draw.spread_step(0.9, 4, opened_by=0.3)


def test_a_shape_with_nowhere_to_open_stays_at_its_first_step() -> None:
    assert draw.spread_step(0.5, 1) == 0, "one step is the only step there is"
    assert draw.spread_step(0.5, 4, opened_by=0.0) == 0, "and an instant opening never starts"


def test_a_stroke_that_would_cover_the_whole_circle_draws_nothing() -> None:
    """A ring fragment needs both ends. A stroke with none is not a ring.

    `draw.arc` cannot be used for this -- it closes the loop whatever angles
    it is given -- which is exactly why this returns early rather than
    drawing the span it was handed: a caller passing a zero-width arc gets
    nothing, rather than a full circle it did not ask for.
    """
    surface = blank((24, 24))

    draw.draw_arc_stroke(surface, (12, 12), 9, 40.0, 40.0, (255, 255, 255), 1)
    draw.draw_arc_stroke(surface, (12, 12), 9, 10.0, 5.0, (255, 255, 255), 1)
    draw.draw_arc_stroke(surface, (12, 12), 0, 10.0, 90.0, (255, 255, 255), 1)

    assert surface.get_at((12, 12))[3] == 0, "nothing drawn, not a stray pixel"


def test_an_ellipse_smaller_than_a_pixel_draws_nothing() -> None:
    """Sub-pixel is not a smaller ellipse, it is a dot, and dots read as dirt."""
    surface = blank((16, 16))

    draw.ellipse_ring(surface, (255, 255, 255), (8, 8), 0.4, 0.4, 1)

    assert all(surface.get_at((x, y))[3] == 0 for x in range(16) for y in range(16)), (
        "an ellipse that cannot hold a pixel leaves the surface alone"
    )


def test_a_shape_with_fewer_than_three_points_is_not_drawn() -> None:
    """Two points make a line, and a line has no interior to fill or rim.

    The two entry points refuse it differently, and both refusals matter. The
    one that draws onto a caller's surface returns and leaves it untouched;
    the one that cuts its own returns a 1x1 rather than `None`, so a caller
    reading the size gets a drawable instead of a crash on `get_at`.
    """
    surface = blank((16, 16))
    draw.draw_inked_polygon(surface, [(2, 2), (8, 8)], (200, 200, 200), (0, 0, 0), 1)
    assert all(surface.get_at((x, y))[3] == 0 for x in range(16) for y in range(16)), (
        "the caller's surface is left exactly as it was"
    )

    cut = draw.inked_polygon([(2, 2), (8, 8)], (200, 200, 200), (0, 0, 0), 1)
    assert cut.get_size() == (1, 1), "a drawable of the smallest size, not a crash"


def test_bounds_of_no_points_still_describe_a_drawable() -> None:
    """`(0, 0, 1, 1)` rather than a zero-size box, which `pygame` rejects."""
    assert draw.polygon_bounds([]) == (0, 0, 1, 1)


def test_a_vertex_with_no_room_to_grow_stays_where_it_is() -> None:
    """A mitre has to be somewhere to go, and two shapes leave it with nowhere.

    A point whose two neighbours sit on top of it has no edge to take a
    normal from, and a point that doubles back on itself has two normals
    pointing opposite ways, which cancel to nothing. Either way there is no
    direction to grow in, and taking one anyway divides by zero: the result
    is a nan, and a nan raises the moment it reaches a `pygame` surface.
    """
    collapsed = draw._offset_polygon([(4, 4), (4, 4), (4, 4)], 1.0)
    assert collapsed == [(4, 4), (4, 4), (4, 4)], "no edge, so no offset"

    spike = draw._offset_polygon([(0, 0), (6, 0), (0, 0)], 1.0)
    assert spike[1] == (6, 0), "two normals that cancel, so no offset either"
    assert all(draw.snap(coordinate) == coordinate for point in spike for coordinate in point), (
        "and what does come back is still whole pixels"
    )


def test_one_step_of_alpha_is_opaque_rather_than_a_division_by_zero() -> None:
    """A single level has no ramp to spread 255 across, so it is simply on."""
    assert draw.life_level(0.5, 0.0, steps=1) == 0
    assert draw.alpha_of_level(0, steps=1) == 255
