"""Whole-pixel drawing primitives for the FX plane.

The game is authored at one pixel per world unit and magnified with
nearest-neighbour ``pygame.transform.scale``, so an anti-aliased surface
would be blurred back into mush by that magnification. What makes a chunky
shape read as deliberate pixel art rather than as jaggies is arithmetic:
whole-pixel coordinates, silhouettes symmetric about their centre, and alpha
that moves in discrete steps. Every primitive here rests on those three
rules, which is why they all snap their own coordinates.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable

import pygame

from src.core.colors import Color, ColorRGBA

__all__ = [
    "ALPHA_STEPS",
    "TRANSPARENT",
    "Shape",
    "alpha_of_level",
    "disc",
    "disc_shape",
    "draw_arc_stroke",
    "draw_inked_polygon",
    "ellipse_ring",
    "ink_shape",
    "polygon_bounds",
    "inked_polygon",
    "life_alpha",
    "life_level",
    "ring",
    "snap",
    "spread_step",
    "star_points",
    "star_shape",
    "streak_points",
]

type Paint = Color | ColorRGBA
type Shape = Callable[[pygame.Surface, Paint, int], None]
"""Draws one silhouette in ``color``, grown outward by ``inflate`` pixels.

The grow argument is what makes a single shape serve twice: the ink pass
draws it grown, the fill pass draws it as it is, and the difference between
the two reads as an outline without a second shape to keep in sync.
"""

TRANSPARENT: ColorRGBA = (0, 0, 0, 0)
ALPHA_STEPS = 8
"""Discrete alpha levels a particle fades through.

Nearest-neighbour magnification turns a smooth 0-255 ramp into a field of
half-transparent pixels that read as dirt. Eight levels cost nothing and
look authored.
"""


def snap(value: float) -> int:
    """``value`` rounded to the nearest whole pixel."""
    return int(math.floor(value + 0.5))


def _center(at: tuple[float, float] | pygame.math.Vector2) -> tuple[int, int]:
    return snap(at[0]), snap(at[1])


def disc(
    surface: pygame.Surface,
    color: Paint,
    at: tuple[float, float] | pygame.math.Vector2,
    radius: float,
) -> None:
    """A filled disc of whole-pixel radius."""
    pygame.draw.circle(surface, color, _center(at), max(1, snap(radius)))


def draw_arc_stroke(
    surface: pygame.Surface,
    at: tuple[float, float],
    radius: float,
    start: float,
    stop: float,
    color: Paint,
    thickness: int = 1,
) -> None:
    """A partial ring between two angles, in degrees.

    ``pygame.draw.arc`` is not usable for this: it ignores both of its angles
    and closes the loop whatever they say, so every span handed to it comes
    back as a full circle. A stroke of the circle's own points is the only way
    to get an arc that actually ends where it was asked to.
    """
    if radius < 1 or stop <= start:
        return
    # One sample per half-degree of arc, not per degree: a fragment of a ring
    # can be a few degrees wide, and sampling per degree rounds the two ends
    # onto the same pixel and the fragment disappears.
    step = 0.5
    points = [
        (
            snap(at[0] + radius * math.cos(math.radians(angle))),
            snap(at[1] + radius * math.sin(math.radians(angle))),
        )
        for angle in _frange(start, stop, step)
    ]
    if len(points) > 1:
        pygame.draw.lines(surface, color, False, points, max(1, thickness))


def _frange(start: float, stop: float, step: float) -> Iterable[float]:
    """``start`` to ``stop`` inclusive, on whole samples of ``step``."""
    count = int(math.floor((stop - start) / step))
    return (start + index * step for index in range(count + 1))


def ring(
    surface: pygame.Surface,
    color: Paint,
    at: tuple[float, float] | pygame.math.Vector2,
    radius: float,
    thickness: float = 1.0,
) -> None:
    """A hollow ring: the outer disc, then the hole punched back out.

    ``pygame.draw`` overwrites on an ``SRCALPHA`` surface, so drawing the
    transparent inner disc removes the pixels rather than tinting them.
    """
    middle = _center(at)
    outer = max(1, snap(radius))
    pygame.draw.circle(surface, color, middle, outer)
    inner = outer - max(1, snap(thickness))
    if inner > 0:
        pygame.draw.circle(surface, TRANSPARENT, middle, inner)


def ellipse_ring(
    surface: pygame.Surface,
    color: Paint,
    at: tuple[float, float] | pygame.math.Vector2,
    rx: float,
    ry: float,
    thickness: float = 1.0,
) -> None:
    """A ring squashed on one axis: an impact read as flat on the ground."""
    middle = _center(at)
    box = pygame.Rect(
        middle[0] - snap(rx),
        middle[1] - snap(ry),
        2 * snap(rx),
        2 * snap(ry),
    )
    if box.width < 1 or box.height < 1:
        return
    pygame.draw.ellipse(surface, color, box, max(1, snap(thickness)))


def disc_shape(
    at: tuple[float, float] | pygame.math.Vector2,
    radius: float,
) -> Shape:
    """A disc as a :data:`Shape`, so it can be inked."""

    def draw(surface: pygame.Surface, color: Paint, inflate: int) -> None:
        disc(surface, color, at, radius + inflate)

    return draw


def star_points(
    at: tuple[float, float] | pygame.math.Vector2,
    outer: float,
    inner: float,
    points: int = 4,
    heading: float = -math.pi / 2.0,
) -> list[tuple[int, int]]:
    """The vertices of a star, as whole pixels.

    ``heading`` is where the first point points, in radians, so a caller
    aiming a sparkle along a velocity passes that velocity's angle.
    """
    cx, cy = _center(at)
    reach = max(1.0, float(outer))
    waist = max(1.0, float(inner))
    step = math.pi / max(2, points)
    vertices: list[tuple[int, int]] = []
    for index in range(points * 2):
        angle = heading - math.pi / 2.0 + index * step
        radius = reach if index % 2 == 0 else waist
        vertices.append((snap(cx + radius * math.cos(angle)), snap(cy + radius * math.sin(angle))))
    return vertices


def star_shape(
    at: tuple[float, float] | pygame.math.Vector2,
    outer: float,
    inner: float,
    points: int = 4,
    heading: float = -math.pi / 2.0,
) -> Shape:
    """A star as a :data:`Shape`."""
    reach = max(1.0, float(outer))
    waist = max(1.0, float(inner))

    def draw(surface: pygame.Surface, color: Paint, inflate: int) -> None:
        pygame.draw.polygon(
            surface,
            color,
            star_points(at, reach + inflate, waist + inflate, points, heading),
        )

    return draw


def streak_points(
    at: tuple[float, float] | pygame.math.Vector2,
    length: float,
    width: float,
    angle: float = 0.0,
    curve: float = 0.0,
    segments: int = 8,
) -> list[tuple[int, int]]:
    """A tapered speed line reaching backwards from ``at``, along ``angle``.

    Built from a handful of chords rather than a smooth outline so the
    silhouette stays chunky: the tip tapers to a point and the thick end is
    flat, which is what a hand-drawn speed line looks like at this scale.
    The taper is faster than linear on purpose -- a speed line that only
    narrows gently reads as a lens, not as something thrown. The thick end
    sits on ``at``, so a caller aiming a line has one anchor to think about.
    """
    reach = max(1.0, float(length))
    thick = max(1.0, float(width))
    step = max(2, segments)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    cx, cy = _center(at)

    def edge(position: float, side: float) -> tuple[int, int]:
        along = -position * reach
        bow = math.sin(position * math.pi) * curve
        across = bow + side * 0.5 * thick * (1.0 - position) ** 1.7
        return (
            snap(cx + along * cos_a - across * sin_a),
            snap(cy + along * sin_a + across * cos_a),
        )

    return [
        *(edge(index / step, 1.0) for index in range(step + 1)),
        *(edge(index / step, -1.0) for index in range(step, -1, -1)),
    ]


def _offset_polygon(points: list[tuple[int, int]], distance: float) -> list[tuple[int, int]]:
    """``points`` pushed outward along the bisector of their two edges.

    A mitre join, which is what an ink rim is: the same outline, one pixel
    out, meeting cleanly at the corners. Scaling the polygon about its own
    centre would be cheaper and visibly wrong -- it cannot lengthen a
    tapered line without also fattening its middle, so a speed line came out
    as a lozenge.
    """
    if distance == 0.0 or len(points) < 3:
        return points
    count = len(points)
    moved: list[tuple[int, int]] = []
    for index in range(count):
        before = points[index - 1]
        here = points[index]
        after = points[(index + 1) % count]
        normals = []
        for origin, end in ((before, here), (here, after)):
            dx, dy = end[0] - origin[0], end[1] - origin[1]
            length = math.hypot(dx, dy)
            if length:
                normals.append((dy / length, -dx / length))
        if not normals:
            moved.append(here)
            continue
        nx = sum(normal[0] for normal in normals)
        ny = sum(normal[1] for normal in normals)
        length = math.hypot(nx, ny)
        if not length:
            moved.append(here)
            continue
        scale = distance * 2.0 / length if length < 2.0 else distance
        moved.append((snap(here[0] + nx / length * scale), snap(here[1] + ny / length * scale)))
    return moved


def polygon_bounds(
    points: Iterable[tuple[float, float]], at: tuple[float, float] = (0, 0)
) -> tuple[int, int, int, int]:
    """The left, top, width and height a set of points needs, with a pixel spare."""
    vertices = [(snap(point[0] + at[0]), snap(point[1] + at[1])) for point in points]
    if not vertices:
        return (0, 0, 1, 1)
    xs = [point[0] for point in vertices]
    ys = [point[1] for point in vertices]
    left, top = min(xs) - 1, min(ys) - 1
    return (left, top, max(1, max(xs) - left + 2), max(1, max(ys) - top + 2))


def draw_inked_polygon(
    surface: pygame.Surface,
    points: Iterable[tuple[float, float]],
    fill: Paint,
    ink: Paint,
    width: int = 1,
    at: tuple[float, float] = (0, 0),
) -> None:
    """Draw a polygon with an ink rim onto ``surface``, at ``at``.

    The rim is the same outline grown outward, so one shape serves both
    passes. Two of the same line, one thick and one thin, are how a comet
    gets a lit core; they have to be drawn in the same frame, which is what
    taking a surface and an offset is for.

    A ``width`` of zero draws only the fill, and an ``ink`` equal to the
    ``fill`` is the same thing done the long way: a shape with no rim, for
    the effects that must not be read as an outlined comic shape.
    """
    vertices = [(snap(point[0] + at[0]), snap(point[1] + at[1])) for point in points]
    if len(vertices) < 3:
        return
    grown = _offset_polygon(vertices, float(width))
    if width > 0:
        pygame.draw.polygon(surface, ink, grown)
    pygame.draw.polygon(surface, fill, vertices)


def inked_polygon(
    points: Iterable[tuple[float, float]],
    fill: Paint,
    ink: Paint,
    width: int = 1,
    at: tuple[float, float] = (0, 0),
) -> pygame.Surface:
    """A polygon with an ink rim, on a surface cut to fit it exactly.

    Sizing the surface from the points is what makes it safe to draw a
    rotated line without guessing how much room its heading needs.
    """
    vertices = [(snap(point[0] + at[0]), snap(point[1] + at[1])) for point in points]
    if len(vertices) < 3:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    grown = _offset_polygon(vertices, float(width))
    xs = [point[0] for point in grown] + [point[0] for point in vertices]
    ys = [point[1] for point in grown] + [point[1] for point in vertices]
    left, top = min(xs) - 1, min(ys) - 1
    surface = pygame.Surface(
        (max(1, max(xs) - left + 2), max(1, max(ys) - top + 2)),
        pygame.SRCALPHA,
    )
    draw_inked_polygon(surface, points, fill, ink, width, at=(-left, -top))
    return surface


def ink_shape(
    surface: pygame.Surface,
    shape: Shape,
    fill: Paint,
    ink: Paint,
    width: int = 1,
) -> None:
    """Draw ``shape`` with a ``width``-pixel ink rim, comic-panel style."""
    shape(surface, ink, width)
    shape(surface, fill, 0)


def life_level(life: float, fade_in: float = 0.0, steps: int = ALPHA_STEPS) -> int:
    """The alpha level index (0 to ``steps - 1``) for a particle at ``life``.

    ``life`` is the elapsed fraction of the particle's span. The envelope
    ramps up over the first ``fade_in`` of the span, so nothing pops into
    existence at full opacity, and then holds before falling away, so a
    particle is bright for most of its life and then goes at once.
    """
    if steps < 2:
        return 0
    if fade_in > 0.0 and life < fade_in:
        level = life / fade_in
    else:
        span = 1.0 - fade_in
        level = (1.0 - (life - fade_in) / span) ** 1.6 if span > 0.0 else 0.0
    index = int(level * (steps - 1) + 0.5)
    return min(steps - 1, max(0, index))


def life_alpha(life: float, fade_in: float = 0.0, steps: int = ALPHA_STEPS) -> int:
    """The alpha a particle at ``life`` should carry, in ``steps`` levels."""
    return alpha_of_level(life_level(life, fade_in, steps), steps)


def spread_step(life: float, steps: int, opened_by: float = 0.45) -> int:
    """The step index of a shape that opens outward over the first of its life.

    Distinct from :func:`life_level`, which is a *fade*: that curve falls
    from full brightness, so indexing it would start a growing shape at its
    largest and shrink it, which is the opposite of opening.
    """
    if steps < 2 or opened_by <= 0.0:
        return 0
    reached = max(0.0, min(1.0, life / opened_by))
    return min(steps - 1, int(reached * steps))


def alpha_of_level(level: int, steps: int = ALPHA_STEPS) -> int:
    """The alpha a level index stands for."""
    if steps < 2:
        return 255
    return min(steps - 1, max(0, level)) * 255 // (steps - 1)
