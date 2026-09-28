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
