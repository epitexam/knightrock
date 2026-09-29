"""The particles themselves: what each one looks like and how it moves.

A particle subclasses :class:`FxParticle`, declares its physics as class
attributes, and paints its pixels once in ``_paint``. Nothing in here knows
about the plane it lands in, the entity that caused it, or the budget that
paid for it -- that is the spawners' half, and keeping the split sharp is
what makes each half testable on its own.

The two rules that decide whether a shape reads as pixel art are implemented
in :mod:`src.core.fx.draw` and every particle here rests on them: whole
pixels, dark ink rims, and alpha in discrete steps.
"""

from __future__ import annotations

import math
import random
from typing import ClassVar

import pygame
from pygame.math import Vector2

from src.core.colors import Color, Colors, FXColors
from src.core.fx.draw import (
    ALPHA_STEPS,
    disc,
    disc_shape,
    draw_arc_stroke,
    ellipse_ring,
    ink_shape,
    inked_polygon,
    life_alpha,
    life_level,
    lobe_shape,
    snap,
    spread_step,
    star_shape,
    streak_points,
)
from src.core.settings import DashDust, Dust, FxDecal, FxDizzy, FxGuard, Sweat


class FxParticle(pygame.sprite.Sprite):
    """One particle: a surface built once, then movement and a stepped fade.

    A subclass declares its physics as class attributes, builds its pixels in
    :meth:`_paint`, and overrides :meth:`_integrate` only when the motion is
    not a straight line. The fade is discrete on purpose: it moves through a
    handful of levels rather than a continuous ramp, and spends the first
    ``fade_in`` of the life ramping up, so a particle never appears out of
    nothing at full opacity.
    """

    gravity: ClassVar[float] = 0.0
    drag: ClassVar[float] = 0.0
    fade_in: ClassVar[float] = 0.0
    alpha_steps: ClassVar[int] = ALPHA_STEPS
    behind: ClassVar[bool] = False
    """Painted under the moving plane, so a fighter is never behind its dust."""
    family: ClassVar[str]
    """The budget this particle spends from. No default on purpose: a
    particle with no family spends from one nobody capped."""

    def __init__(self, pos: tuple[float, float] | Vector2, ttl: float) -> None:
        super().__init__()
        self.pos = Vector2(pos)
        self.velocity = Vector2(0.0, 0.0)
        self.ttl = float(ttl)
        self.max_ttl = float(ttl) if ttl > 0.0 else 1.0
        self.image: pygame.Surface = self._paint()
        self.rect: pygame.FRect = self.image.get_frect(center=self.pos)

    @property
    def life(self) -> float:
        """The share of the span elapsed, from 0 to 1."""
        return 1.0 - self.ttl / self.max_ttl

    def _paint(self) -> pygame.Surface:
        raise NotImplementedError

    def _integrate(self, delta_time: float) -> None:
        if self.drag > 0.0:
            self.velocity.x *= max(0.0, 1.0 - self.drag * delta_time)
        if self.gravity != 0.0:
            self.velocity.y += self.gravity * delta_time
        self.pos += self.velocity * delta_time

    def _fade(self) -> None:
        self.image.set_alpha(life_alpha(self.life, self.fade_in, self.alpha_steps))

    def update(self, delta_time: float) -> None:
        self.ttl -= delta_time
        if self.ttl <= 0.0:
            self.kill()
            return
        self._integrate(delta_time)
        self._fade()
        self.rect = self.image.get_frect(center=self.pos)


class DustParticle(FxParticle):
    family: ClassVar[str] = "landing_dust"

    """A puff of dust, kicked out of the feet and spreading as it dies.

    The puff used to be a single disc that faded, which read as a ball being
    switched off, and its size was ignored outright: the shipped debris frames
    are a fixed 30px scaled by a constant, so a soft landing and a hard one
    produced byte-identical pixels and only the velocity told them apart.

    It is now a cloud of a few overlapping discs that opens over its life,
    picked from a ladder shared by every puff of the same size. Six puffs on
    a landing are six references into a table rather than six painted
    surfaces, which is what keeps a fan affordable.
    """

    gravity: ClassVar[float] = Dust.RISE
    drag: ClassVar[float] = Dust.DRAG
    fade_in: ClassVar[float] = Dust.FADE_IN
    behind: ClassVar[bool] = True

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = Dust.TTL,
        radius: float = Dust.PUFF_RADIUS,
        tint: float = 0.0,
    ) -> None:
        self.radius = float(radius)
        self.tint = float(tint)
        self.ladder = puff_frames(self.radius, self.tint)
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)
        self.image = self.ladder[0]
        self.rect = self.image.get_frect(center=self.pos)

    def _paint(self) -> pygame.Surface:
        return self.ladder[0]

    def _integrate(self, delta_time: float) -> None:
        super()._integrate(delta_time)
        self.image = self.ladder[spread_step(self.life, len(self.ladder), Dust.PUFF_STEP_OPENS)]


class DashDustParticle(FxParticle):
    family: ClassVar[str] = "dash_dust"

    """A cloud of dust a dash leaves behind it.

    The dash is the fastest thing in the game -- 1100 px/s for 0.08s -- and
    until now the only thing marking it was the renderer's afterimages, which
    photograph the fighter and draw nothing beside it. Nothing in the plane
    said the fighter had displaced anything.

    So this is the mark the dash was missing, and it is deliberately one
    thing. The dash once had five systems on the same 80ms event and the frame
    they produced was a white cloud under a stretched rectangle with a hoop
    around it; a trail and nothing else is the part of that worth keeping.

    Drawn without an ink rim, in two tones. The block's ring gave up its rim
    for the same reason this does: a mid-grey outline at one pixel per world
    unit turns a mark into a drawn shape with nothing light about it, and a
    single flat tone is a blob. So the separation is carried by a lit lobe set
    into the cloud, the way the block carries it on the side that was struck.

    Animates by stepping a ladder shared with every puff of the same size and
    tone, for the same reason the landing dust does and for the same cost: a
    dash lays a ribbon of these at once, so they have to be references into a
    table rather than surfaces allocated on the tick.
    """

    gravity: ClassVar[float] = DashDust.RISE
    drag: ClassVar[float] = DashDust.DRAG
    fade_in: ClassVar[float] = DashDust.FADE_IN
    behind: ClassVar[bool] = True

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = DashDust.TICK_TTL,
        radius: float = DashDust.TICK_RADIUS,
        tint: float = 0.0,
    ) -> None:
        self.radius = float(radius)
        self.tint = float(tint)
        self.ladder = dash_frames(self.radius, self.tint)
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)
        self.image = self.ladder[0]
        self.rect = self.image.get_frect(center=self.pos)

    def _paint(self) -> pygame.Surface:
        return self.ladder[0]

    def _integrate(self, delta_time: float) -> None:
        super()._integrate(delta_time)
        self.image = self.ladder[spread_step(self.life, len(self.ladder), DashDust.STEP_OPENS)]


class OrbitParticle(FxParticle):
    family: ClassVar[str] = "dizzy_star"

    """A star circling a point, for as long as the stun lasts.

    It orbits rather than falls. The dizzy stars used to be ordinary sparks,
    so the gravity that reads well on a spark dragged the whole constellation
    through the floor over the course of a long stun. The position is a
    function of the elapsed time, which makes the movement exactly
    reproducible and costs no integration.
    """

    fade_in: ClassVar[float] = FxDizzy.STAR_FADE_IN

    def __init__(
        self,
        center: tuple[float, float] | Vector2,
        radius: float,
        phase: float,
        speed: float,
        color: Color,
        core: Color,
        ttl: float,
        size: float = 5.0,
        bob: float = 0.0,
    ) -> None:
        self.orbit_center = Vector2(center)
        self.radius = float(radius)
        self.phase = float(phase)
        self.speed = float(speed)
        self.color = color
        self.core = core
        self.size = float(size)
        self.bob = float(bob)
        super().__init__(self._place(0.0), ttl)

    def _place(self, age: float) -> Vector2:
        angle = self.phase + self.speed * age
        return (
            self.orbit_center
            + Vector2((self.radius * math.cos(angle), self.radius * math.sin(angle) * 0.45))
            + Vector2((0.0, self.bob * math.sin(angle * 2.0)))
        )

    def _paint(self) -> pygame.Surface:
        side = snap(self.size) * 2 + 6
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        middle = (side / 2.0, side / 2.0)
        ink_shape(
            surface,
            star_shape(middle, self.size, self.size * 0.34, 4, self.phase),
            self.color,
            FXColors.ink_warm,
            1,
        )
        ink_shape(
            surface,
            star_shape(middle, self.size * 0.45, self.size * 0.2, 4, self.phase),
            self.core,
            self.color,
            0,
        )
        return surface

    def _integrate(self, delta_time: float) -> None:
        self.pos = self._place(self.life * self.max_ttl)


class DizzyVortexParticle(FxParticle):
    family: ClassVar[str] = "dizzy_vortex"

    """A purple swirl at the feet of a dizzy entity.

    The swirl is a shared ladder of rotation steps: it used to redraw three
    arms of three polygons per particle per frame, and a stun puts up to four
    of them on screen at once.
    """

    fade_in: ClassVar[float] = FxDizzy.VORTEX_FADE_IN

    def __init__(self, pos: tuple[float, float] | Vector2, ttl: float = FxDizzy.VORTEX_TTL) -> None:
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        return vortex_frames()[0]

    def _integrate(self, delta_time: float) -> None:
        self.image = vortex_frames()[life_level(self.life, 0.0, FxDizzy.VORTEX_FRAMES)]


class ImpactDecalParticle(FxParticle):
    family: ClassVar[str] = "impact_decal"

    """The mark a hard landing leaves on the ground.

    Still, short-lived, and behind the moving plane: the puffs say how hard
    the landing was, this says where.

    It used to be three thick tongues at 0, 120 and 240 degrees, which came
    out as a lopsided comma rather than a mark on a floor -- asymmetric
    about a vertical that means nothing here, and five pixels thick against a
    fighter forty wide. It is a flat ring now, opening outward over its first
    moments: a squashed circle reads as the floor being struck, and it opens
    the way a real mark does instead of sitting there at one size.

    The ladder is built per spawn rather than shared, because it is scaled by
    the fall speed and a landing is rare. Sharing it would mean snapping the
    width to a bucket, and a decal whose width jumped between neighbouring
    falls would say less than one that is smoothly wrong.
    """

    behind: ClassVar[bool] = True
    fade_in: ClassVar[float] = FxDecal.FADE_IN

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        ttl: float = FxDecal.TTL,
        width: float = FxDecal.RADIUS,
    ) -> None:
        self.width = float(width)
        self.steps = [self._mark(step) for step in range(FxDecal.RING_STEPS)]
        super().__init__(pos, ttl)
        self.image = self.steps[0]
        self.rect = self.image.get_frect(center=self.pos)

    def _mark(self, step: int) -> pygame.Surface:
        """The mark at one moment of opening, ``step`` of ``RING_STEPS``."""
        reach = self.width * (1.0 + FxDecal.RING_GROWTH * step)
        # Radius plus the widest it gets, or the last ring is drawn off the
        # edge of its own surface.
        span = 2 * (snap(reach) + FxDecal.MARGIN)
        surface = pygame.Surface((span, span), pygame.SRCALPHA)
        middle = span / 2.0
        ellipse_ring(
            surface,
            FXColors.decal,
            (middle, middle),
            reach,
            reach * FxDecal.RING_SQUASH,
            FxDecal.RING_THICKNESS - step,
        )
        return surface

    def _paint(self) -> pygame.Surface:
        return self.steps[0]

    def _integrate(self, delta_time: float) -> None:
        self.image = self.steps[spread_step(self.life, len(self.steps), FxDecal.RING_STEP_OPENS)]


class ShieldArcParticle(FxParticle):
    family: ClassVar[str] = "shield_arc"

    """The block: one fine ring, brighter where the hit landed.

    A hairline rather than an inked band. The rim it used to carry was a
    comic-panel outline, five pixels of it, and at this size the ring read as
    a heavy drawn shape with nothing light about it. One thin stroke plus a
    short brighter kick on the side the block came from says the same thing
    -- a shield taking a hit, from a direction -- with a fifth of the ink.
    """

    fade_in: ClassVar[float] = FxGuard.ARC_FADE_IN

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        side: float,
        parried: bool = False,
        ttl: float = FxGuard.ARC_TTL,
    ) -> None:
        self.side = 1.0 if side >= 0.0 else -1.0
        self.body = FXColors.parry_spark if parried else FXColors.shield_arc
        self.kick = FXColors.parry_core if parried else Colors.off_white
        self.parried = parried
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        """A one-pixel ring, and a two-pixel kick over the side that was hit.

        Drawn with ``pygame.draw.circle`` rather than ``draw.arc``, which
        ignores its start and stop angles and closes the loop whatever they
        say -- every set of spans handed to it produced the same full ring.
        """
        radius = snap(FxGuard.ARC_RADIUS)
        side = 2 * radius + FxGuard.ARC_MARGIN
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        middle = side / 2.0
        pygame.draw.circle(surface, self.body, (snap(middle), snap(middle)), radius, 1)
        facing = 0.0 if self.side >= 0.0 else 180.0
        draw_arc_stroke(
            surface,
            (snap(middle), snap(middle)),
            radius,
            facing - FxGuard.ARC_FLASH,
            facing + FxGuard.ARC_FLASH,
            self.kick,
            FxGuard.ARC_KICK_WIDTH,
        )
        return surface


class ShatterArcParticle(FxParticle):
    family: ClassVar[str] = "shatter_arc"

    """The block's ring, coming apart into its own pieces.

    Both halves of the blocked-hit silhouette are the same thing failing: the
    ring is cut into fragments that drift apart, and the bright kick on the hit
    side is cut into finer ones that travel furthest, because that is the side
    that gave way. At the first step the circle is whole, so the effect reads
    as one object breaking rather than as debris that happened to be round.

    Pre-rendered per spawn, in steps: a break is rare, and the geometry is the
    expensive part, so paying it once beats rebuilding it every tick.
    """

    fade_in: ClassVar[float] = 0.0

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        side: float,
        ttl: float = FxGuard.SHARD_TTL,
        seed: int = 0,
    ) -> None:
        self.side = 1.0 if side >= 0.0 else -1.0
        self.steps = [
            self._shatter(index / (FxGuard.SHARD_STEPS - 1), seed)
            for index in range(FxGuard.SHARD_STEPS)
        ]
        super().__init__(pos, ttl)
        self.image = self.steps[0]

    def _fragment(
        self,
        surface: pygame.Surface,
        middle: float,
        middle_angle: float,
        half_span: float,
        radius: float,
        color: Color,
    ) -> None:
        """One arc-shaped piece of the ring, at its own radius."""
        draw_arc_stroke(
            surface,
            (middle, middle),
            radius,
            middle_angle - half_span,
            middle_angle + half_span,
            color,
            1,
        )

    def _shatter(self, progress: float, seed: int) -> pygame.Surface:
        """The ring at one moment of its failure, ``progress`` from 0 to 1."""
        radius = snap(FxGuard.SHARD_RADIUS)
        # Radius plus the furthest a piece can travel, or the circle is drawn
        # off the edge of its own surface.
        reach = snap(radius * (1.0 + FxGuard.SHARD_SPREAD * (1.0 + FxGuard.SHARD_WOUND_PUSH)))
        span = 2 * (reach + FxGuard.SHARD_MARGIN)
        surface = pygame.Surface((span, span), pygame.SRCALPHA)
        middle = span / 2.0
        rng = random.Random(seed * 977 + FxGuard.SHARD_PIECES)
        facing = 0.0 if self.side >= 0.0 else 180.0
        spread = FxGuard.SHARD_SPREAD * progress

        slot = 360.0 / FxGuard.SHARD_PIECES
        for index in range(FxGuard.SHARD_PIECES):
            centre = facing + index * slot + slot / 2.0
            on_wound = _angle_near(centre, facing, FxGuard.SHARD_WOUND)
            thrown = (
                spread
                * (1.0 + FxGuard.SHARD_WOUND_PUSH * on_wound)
                * rng.uniform(*FxGuard.SHARD_DRIFT)
            )
            self._fragment(
                surface,
                middle,
                centre,
                slot / 2.0 * (1.0 - FxGuard.SHARD_SHRINK * progress),
                radius + radius * thrown,
                FXColors.break_spark,
            )

        fine = FxGuard.ARC_FLASH
        piece = fine / FxGuard.SHARD_KICK_PIECES
        for index in range(FxGuard.SHARD_KICK_PIECES):
            centre = facing - fine / 2.0 + piece * (index + 0.5)
            thrown = (
                spread * (1.0 + FxGuard.SHARD_WOUND_PUSH) * rng.uniform(*FxGuard.SHARD_KICK_DRIFT)
            )
            self._fragment(
                surface,
                middle,
                centre,
                piece / 2.0 * (1.0 - FxGuard.SHARD_SHRINK * 1.3 * progress),
                radius + radius * thrown,
                FXColors.break_core,
            )
        return surface

    def _paint(self) -> pygame.Surface:
        return self.steps[0]

    def _integrate(self, delta_time: float) -> None:
        self.image = self.steps[spread_step(self.life, len(self.steps), FxGuard.SHARD_STEP_OPENS)]


def _angle_near(angle: float, centre: float, span: float) -> float:
    """How much of ``span`` an angle sits inside, from 0 (outside) to 1 (dead on).

    Wrapping, because the ring's angles run past 360 and the wound is on
    whichever side the guard faces.
    """
    half = span / 2.0
    offset = abs(((angle - centre + 180.0) % 360.0) - 180.0)
    return max(0.0, 1.0 - offset / half)


class SweatParticle(FxParticle):
    family: ClassVar[str] = "sweat"

    """A comic teardrop popped off the head of an exhausted dasher.

    Heavier than dust, so the pop is immediately fought by gravity and the
    drop traces a short nervous fountain before winking out. Fat, inked and
    glossed: it has to read as a bead of liquid at gameplay distance.
    """

    gravity: ClassVar[float] = Sweat.GRAVITY
    fade_in: ClassVar[float] = Sweat.FADE_IN

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = Sweat.TTL,
        radius: float = Sweat.RADIUS,
        tint: float = 0.0,
    ) -> None:
        self.radius = float(radius)
        self.tint = float(tint)
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)

    def _paint(self) -> pygame.Surface:
        radius = int(self.radius)
        outline = Sweat.OUTLINE_WIDTH
        margin = Sweat.MARGIN
        width = 2 * (radius + outline + margin)
        height = radius + 2 * radius + 2 * outline + 2 * margin
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        cx = width // 2
        bulb = height - margin - outline - radius
        body = _shade(FXColors.sweat, self.tint)
        ink_shape(
            surface,
            disc_shape((cx, bulb), float(radius)),
            body,
            FXColors.sweat_ink,
            outline,
        )
        pygame.draw.polygon(
            surface,
            FXColors.sweat_ink,
            [
                (cx, margin - outline),
                (cx + radius + outline, bulb - radius // 2),
                (cx - radius - outline, bulb - radius // 2),
            ],
        )
        pygame.draw.polygon(
            surface,
            body,
            [
                (cx, margin + outline),
                (cx + radius - outline // 2, bulb - radius // 2),
                (cx - radius + outline // 2, bulb - radius // 2),
            ],
        )
        disc(
            surface,
            _shade(FXColors.sweat_shine, self.tint),
            (cx - radius // 2, bulb - radius // 3),
            max(1.0, radius / 3.0),
        )
        return surface


def _shade(color: Color, amount: float) -> Color:
    """``color`` lifted toward white by ``amount``, for per-particle variety."""
    lift = min(1.0, max(0.0, amount))
    if lift <= 0.0:
        return color
    return (
        min(255, snap(color[0] + (255 - color[0]) * lift)),
        min(255, snap(color[1] + (255 - color[1]) * lift)),
        min(255, snap(color[2] + (255 - color[2]) * lift)),
    )


_puff_cache: dict[tuple[int, float], list[pygame.Surface]] = {}
_dash_cache: dict[tuple[int, float], list[pygame.Surface]] = {}
_vortex_cache: list[pygame.Surface] = []


def _nearest_bucket(radius: float, buckets: tuple[int, ...]) -> int:
    """The entry of ``buckets`` whose radius is closest to ``radius``.

    Nearest rather than rounded down, and never below the table's floor: a
    puff asked for at less than the smallest still gets the smallest, so a
    ladder has one row per bucket rather than growing a new one per radius
    anyone asked for.
    """
    reach = max(0.0, float(radius))
    return min(buckets, key=lambda bucket: abs(bucket - reach))


def _puff_bucket(radius: float) -> int:
    """The landing ladder entry whose radius a puff of ``radius`` should use."""
    return _nearest_bucket(radius, Dust.PUFF_BUCKETS)


def _dash_bucket(radius: float) -> int:
    """The trail ladder entry whose radius a puff of ``radius`` should use."""
    return _nearest_bucket(radius, DashDust.BUCKETS)


def _puff_step(radius: float, step: int, tint: float) -> pygame.Surface:
    """One step of the billow: the cloud at its size for this step.

    Drawn at the radius it has *become* rather than the one it started at, so
    the ladder is the growth. The first step is squashed flat because that is
    the shape dust has while it is still leaving the floor, and the squash
    relaxes to nothing over the ladder.
    """
    opened = 1.0 + Dust.PUFF_GROWTH * step
    reach = radius * opened
    body = _shade(FXColors.dust, tint)
    ink = _shade(FXColors.dust_deep, tint)
    # The cloud's own reach, plus the rim, plus the lit lobe's offset: the
    # surface is cut for the widest thing drawn on it, not for the nominal
    # radius, or the satellites and the rim fall off the edge.
    margin = max(1.0, max(abs(x) + share for x, _, share in Dust.PUFF_LOBES)) * radius * opened
    span = 2 * (snap(reach + margin) + 2)
    surface = pygame.Surface((span, span), pygame.SRCALPHA)
    middle = span / 2.0
    squash = 1.0 - (1.0 - Dust.PUFF_SQUASH) * max(0.0, 1.0 - step)
    lobes = tuple(
        (offset_x * reach, offset_y * reach * squash, share * reach)
        for offset_x, offset_y, share in Dust.PUFF_LOBES
    )
    ink_shape(surface, lobe_shape((middle, middle), lobes), body, ink, 1)
    # The lit side, set into the top-left of the cloud. A puff with no light
    # on it is a hole in the background rather than a mass of dust.
    disc(
        surface,
        _shade(body, Dust.PUFF_CORE_LIFT),
        (middle - reach * Dust.PUFF_CORE, middle - reach * Dust.PUFF_CORE * squash),
        max(1.0, reach * Dust.PUFF_CORE),
    )
    return surface


def puff_tint(index: int) -> float:
    """The body tone the puff at ``index`` in a fan is drawn in.

    Cycled rather than drawn, because the ladder is keyed on tone as well as
    radius: a fan of six clouds in six identical greys reads as a stamped
    pattern, and a row of near-identical tones is what a spot-on-the-eye
    randomiser would give. Indexed modulo the palette, so the caller can hand
    it the puff index directly.
    """
    tints = _puff_tints()
    return tints[index % len(tints)]


def _puff_tints() -> tuple[float, ...]:
    """The body shifts a fan is drawn from, evenly across ``Dust.PUFF_TINT``.

    Discrete, one per slot in ``Dust.SIZE_PROFILE``, and keyed into the ladder
    rather than blended at paint time, so a tone costs a cached row instead of
    a surface per particle.
    """
    low, high = Dust.PUFF_TINT
    count = max(1, len(Dust.SIZE_PROFILE))
    if count < 2:
        return (low,)
    span = high - low
    return tuple(low + span * index / (count - 1) for index in range(count))


def puff_frames(radius: float, tint: float = 0.0) -> list[pygame.Surface]:
    """The shared billow of every puff of about ``radius``, in one body tone.

    A puff animates by stepping a ladder rather than by redrawing its cloud,
    and the ladder is keyed on the discrete radii in ``Dust.PUFF_BUCKETS``
    and the discrete tones in ``Dust.PUFF_TINT``, built once per session.
    That is what makes a fan of six affordable: six puffs of similar size and
    tone are references into the same rows, not six sets of surfaces
    allocated at the moment of landing.

    A continuous radius would mean a surface per particle, which is the
    allocation ``notes/refacto.md`` already flags as the FX plane's main
    remaining cost, and a landing is exactly when six of them happen at once.
    A display format change invalidates the cache along with everything else.
    """
    key = (_puff_bucket(radius), round(tint, 3))
    cached = _puff_cache.get(key)
    if cached is not None:
        return cached
    ladder = [_puff_step(key[0], step, tint) for step in range(Dust.PUFF_STEPS)]
    _puff_cache[key] = ladder
    return ladder


def _dash_step(radius: float, step: int, tint: float) -> pygame.Surface:
    """One step of the trail: the cloud at its size for this step.

    The landing puff's step with the ink pass dropped, and its lit lobe taken
    from the palette instead of lifted off the body. The lobes are the same
    union and the first step is the same flat, both for the reason they are on
    the landing: a disc reads as a ball, and dust leaves the ground flat and
    rounds off as it rises.

    What is different is what separates the cloud from the background. The
    landing puff answers that with a rim, which is right for a mark sitting on
    tiles and wrong for one hanging on open air. This answers it with a second
    tone drawn from the palette, so the gap between the two is a designed
    number rather than the product of a lift applied to a lift.
    """
    opened = 1.0 + DashDust.GROWTH * step
    reach = radius * opened
    body = _shade(FXColors.dust, tint)
    margin = max(1.0, max(abs(x) + share for x, _, share in DashDust.LOBES)) * radius * opened
    span = 2 * (snap(reach + margin) + 2)
    surface = pygame.Surface((span, span), pygame.SRCALPHA)
    middle = span / 2.0
    squash = 1.0 - (1.0 - DashDust.SQUASH) * max(0.0, 1.0 - step)
    lobes = tuple(
        (offset_x * reach, offset_y * reach * squash, share * reach)
        for offset_x, offset_y, share in DashDust.LOBES
    )
    lobe_shape((middle, middle), lobes)(surface, body, 0)
    disc(
        surface,
        _shade(FXColors.dust_lit, tint),
        (middle - reach * DashDust.HIGHLIGHT, middle - reach * DashDust.HIGHLIGHT * squash),
        max(1.0, reach * DashDust.HIGHLIGHT),
    )
    return surface


def dash_tint(index: int, count: int) -> float:
    """The body tone the trail puff at ``index`` of ``count`` is drawn in.

    Spread across ``DashDust.TINT`` by the emission's own length rather than
    against a fixed palette. The burst and the ticks are different lengths, so
    a fixed row would draw a two-puff tick as two adjacent tones -- two
    near-identical clouds -- and leave the top of the range unused on the
    burst that is the one mark the whole dash is read from.
    """
    low, high = DashDust.TINT
    if count < 2:
        return low
    return low + (high - low) * index / (count - 1)


def dash_frames(radius: float, tint: float = 0.0) -> list[pygame.Surface]:
    """The shared billow of every trail puff of about ``radius``, in one tone.

    The landing ladder's contract, and the reason for it applies twice over
    here. A dash lays puffs on a cadence rather than in a single fan, so there
    are more of them alive at once, and a continuous radius would mean a
    surface per particle -- exactly the allocation ``notes/refacto.md``
    flags as the plane's main remaining cost. Keyed on the discrete radii in
    ``DashDust.BUCKETS`` and the discrete tones in ``DashDust.TINT``, and
    built once per session.

    A display format change invalidates the cache along with everything else.
    """
    key = (_dash_bucket(radius), round(tint, 3))
    cached = _dash_cache.get(key)
    if cached is not None:
        return cached
    ladder = [_dash_step(key[0], step, tint) for step in range(DashDust.STEPS)]
    _dash_cache[key] = ladder
    return ladder


def vortex_frames() -> list[pygame.Surface]:
    """The shared rotation steps of the dizzy swirl, built once per session.

    A pinwheel of three curved arms: three of them are the only count that
    tiles a full turn without the arms touching, and the curve is what makes
    it read as a swirl rather than as three commas. Every vortex on screen
    shows the same swirl at a different step, so the steps are memoized
    rather than rebuilt per particle. A display format change invalidates
    them along with everything else.
    """
    global _vortex_cache
    if _vortex_cache:
        return _vortex_cache
    radius = FxDizzy.VORTEX_RADIUS
    side = 2 * (snap(radius) + 4)
    middle = (side / 2.0, side / 2.0)
    frames: list[pygame.Surface] = []
    for step in range(FxDizzy.VORTEX_FRAMES):
        turn = step * 2.0 * math.pi / FxDizzy.VORTEX_FRAMES
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        for arm in range(FxDizzy.VORTEX_ARMS):
            heading = turn + arm * 2.0 * math.pi / FxDizzy.VORTEX_ARMS
            short, long = FxDizzy.VORTEX_ARM_REACH
            reach = radius * (short + (long - short) * (arm % 2))
            arm_surface = inked_polygon(
                streak_points(
                    (0, 0),
                    reach,
                    FxDizzy.VORTEX_ARM_THICKNESS,
                    heading,
                    reach * FxDizzy.VORTEX_ARM_CURVE,
                ),
                FXColors.vortex,
                FXColors.vortex_ink,
                1,
                at=middle,
            )
            surface.blit(arm_surface, (0, 0))
        frames.append(surface)
    _vortex_cache = frames
    return frames


def clear_frame_cache() -> None:
    """Forget the memoized ladders, so a new display format repaints them.

    A display format change (``pygame.display.set_mode``) invalidates every
    converted surface, so this cache layer has to be dropped with
    ``AssetLibrary`` or it would keep handing back stale ones.
    """
    global _vortex_cache
    _puff_cache.clear()
    _dash_cache.clear()
    _vortex_cache = []
