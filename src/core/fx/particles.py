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
    Shape,
    ShapeAt,
    disc,
    disc_shape,
    draw_arc_stroke,
    ellipse_ring,
    ink_shape,
    inked_polygon,
    life_alpha,
    life_level,
    mote_shape,
    shape_shaded,
    snap,
    speck,
    spread_step,
    star_shape,
    streak_points,
)
from src.core.settings import (
    DashDust,
    Dust,
    DustGrain,
    FootstepDust,
    FxDecal,
    FxDizzy,
    FxGuard,
    Sweat,
)


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
    alpha_ceiling: ClassVar[int] = 255
    """The most opaque this particle is ever drawn, on a scale of 0 to 255.

    A separate knob from ``alpha_steps`` because a shorter ladder is not a
    dimmer one. :func:`life_alpha` puts the top of whatever ladder it is given
    at full opacity, so three steps is three levels ending at 255 -- a coarser
    fade, not a fainter particle. Dust that has been thrown into the air is a
    haze, and a haze that reaches 255 is a chip of stone, so the grain family
    needs a ceiling and the rest of the plane is content with the default.
    """
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
        self.image.set_alpha(
            min(self.alpha_ceiling, life_alpha(self.life, self.fade_in, self.alpha_steps))
        )

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

    """A sheet of dust, kicked out of the feet and spreading as it dies.

    The puff used to be a single disc that faded, which read as a ball being
    switched off, and its size was ignored outright: the shipped debris frames
    are a fixed 30px scaled by a constant, so a soft landing and a hard one
    produced byte-identical pixels and only the velocity told them apart.

    It then became four large overlapping discs with a disc of highlight set
    into the top left of the lot, which read as a bubble instead: the union of
    four comparable discs is one smooth convex ellipse whatever you do with
    them, and a round patch of light inside a round mass is the drawing
    convention for a shiny cartoon thing. So it is a band of many small lobes
    with a notched top, one pixel of rim light along the top of all of them
    and a pixel of shadow underneath.

    It animates by stepping a ladder shared by every puff of the same size,
    tone and silhouette, so four puffs on a landing are four references into a
    table rather than four painted surfaces.
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
        variant: int = 0,
    ) -> None:
        self.radius = float(radius)
        self.tint = float(tint)
        self.variant = int(variant)
        self.ladder = puff_frames(self.radius, self.tint, self.variant)
        # No image or rect after the super().__init__: ``_paint`` returns
        # ``ladder[0]``, which is what the base put on the sprite and sized the
        # rect from. Setting it again re-fetched the same surface and built a
        # second rect off it, per puff, on the hottest emitter in the plane.
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)

    def _paint(self) -> pygame.Surface:
        return self.ladder[0]

    def _integrate(self, delta_time: float) -> None:
        super()._integrate(delta_time)
        self.image = self.ladder[spread_step(self.life, len(self.ladder), Dust.PUFF_STEP_OPENS)]


class DashDustParticle(FxParticle):
    family: ClassVar[str] = "dash_dust"

    """A sheet of dust a dash leaves behind it.

    The dash is the fastest thing in the game -- 1100 px/s for 0.08s -- and
    until now the only thing marking it was the renderer's afterimages, which
    photograph the fighter and draw nothing beside it. Nothing in the plane
    said the fighter had displaced anything.

    So this is the mark the dash was missing, and it is deliberately one
    thing. The dash once had five systems on the same 80ms event and the frame
    they produced was a white cloud under a stretched rectangle with a hoop
    around it; a trail and nothing else is the part of that worth keeping.

    Drawn without an ink rim and without a shadow, in two tones. The block's
    ring gave up its rim for the same reason this does: a mid-grey outline at
    one pixel per world unit turns a mark into a drawn shape with nothing
    light about it, and a single flat tone is a blob. So the separation is
    carried by a lit edge along the top of the cloud, the way the block carries
    it on the side that was struck.

    Animates by stepping a ladder shared with every puff of the same size, tone
    and silhouette, for the same reason the landing dust does and for the same
    cost: a dash lays a ribbon of these at once, so they have to be references
    into a table rather than surfaces allocated on the tick.
    """

    gravity: ClassVar[float] = DashDust.GRAVITY
    drag: ClassVar[float] = Dust.DRAG
    fade_in: ClassVar[float] = DashDust.FADE_IN
    behind: ClassVar[bool] = True

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = DashDust.TICK_TTL,
        radius: float = DashDust.TICK_RADIUS,
        tint: float = 0.0,
        variant: int = 0,
    ) -> None:
        self.radius = float(radius)
        self.tint = float(tint)
        self.variant = int(variant)
        self.ladder = dash_frames(self.radius, self.tint, self.variant)
        # As with the landing sheet: the base paints ``ladder[0]`` and sizes the
        # rect from it, so there is nothing to set afterwards.
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)

    def _paint(self) -> pygame.Surface:
        return self.ladder[0]

    def _integrate(self, delta_time: float) -> None:
        super()._integrate(delta_time)
        self.image = self.ladder[spread_step(self.life, len(self.ladder), DashDust.STEP_OPENS)]


class FootstepDustParticle(DashDustParticle):
    family: ClassVar[str] = "footstep_dust"

    """A puff off one foot, for a fighter who is merely walking.

    The plane's third dust mark, and the only one that is neither an event nor a
    movement: the landing answers "how hard was that" and the trail answers
    "that was a shove". This one answers the question the other two leave open,
    which is whether the fighter is moving at all -- before it, a fighter at
    full run along a floor left nothing behind him, so the most continuous
    movement in the game was the one that displaced nothing on screen.

    It is the trail's particle, not a smaller one. Same ladder, same two tones,
    same absent rim, same downward gravity, and the rim is absent for the same
    reason the trail's is: this is dust hanging in the air being read as light,
    and a mid-grey outline at one pixel per world unit turns it into a drawn
    shape with nothing light about it. The landing sheet keeps its rim because
    it sits on the tiles, where the edge does the work; a footstep's puff does
    not sit on anything, it is thrown up off the floor and it is gone.

    What it borrows and what it does not is worth being explicit about, because
    the inheritance is the whole of the difference. Inherited: gravity, drag,
    the ladder and ``behind``. Not inherited: the family, which is why this
    exists as a class rather than a flag, and the fade-in, which is a shade
    quicker because a step is born behind a fighter who is already leaving it.

    A subclass rather than a second ladder on purpose. The sheet geometry is
    keyed on size, tone and silhouette, and a footstep's radius lands in the
    same bucket as a dash tick's -- in the first one, which is the smallest
    there is -- so the two share the frames the first one built. Painting a
    second set would double the table for a mark that is not merely similar to
    the trail's but is the same cloud, on a different schedule.

    That is also why there is no radius knob on ``FootstepDust``: the ladder is
    drawn at the nearest of its discrete sizes, so every request under the
    second bucket produces identical pixels and a mark scaled by ground speed
    would move a number and not the screen.
    """

    fade_in: ClassVar[float] = FootstepDust.FADE_IN
    gravity: ClassVar[float] = FootstepDust.GRAVITY
    drag: ClassVar[float] = FootstepDust.DRAG

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = FootstepDust.TTL,
        radius: float = FootstepDust.RADIUS,
        tint: float = 0.0,
        variant: int = 0,
    ) -> None:
        super().__init__(pos, velocity, ttl=ttl, radius=radius, tint=tint, variant=variant)


class GrainParticle(FxParticle):
    family: ClassVar[str] = "dust_grain"

    """One speck of the spray thrown around a landing or a dash.

    The family that makes the sheets read as dust. A kick off a floor does not
    throw a handful of clouds and nothing else: it throws a spray of small
    particles that travel further than the mass does, arrive first, and are
    gone long before it, and a mark with no spray around it is a puff of smoke
    however it is shaded.

    Three things separate a grain from a smaller puff, and all three are here.
    Its surface is a handful of pixels rather than a shape, so it carries no
    silhouette -- there is nothing at two pixels across for the eye to read as
    an outline, which is the point: a spray is judged by its distribution and
    not by any one of its members. It is never opaque, because its alpha
    ceiling sits well under 255 and dust in the air is a haze, not a chip of
    stone -- a ceiling rather than a shorter fade ladder, since the top of
    every ladder is full opacity. And it falls much faster than the mass it
    came from, having nothing holding it up.

    Painted in its own tiny surface at construction, with no ladder and no
    cache, which is what :class:`SweatParticle` does and for the same reason:
    at three pixels square a surface is nine pixels, so sharing one across the
    session would cost a dictionary lookup to save nothing.
    """

    gravity: ClassVar[float] = DustGrain.GRAVITY
    drag: ClassVar[float] = DustGrain.DRAG
    fade_in: ClassVar[float] = DustGrain.FADE_IN
    alpha_steps: ClassVar[int] = DustGrain.ALPHA_STEPS
    alpha_ceiling: ClassVar[int] = DustGrain.MAX_ALPHA
    behind: ClassVar[bool] = True

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        size: int = 1,
        tint: float = 0.0,
    ) -> None:
        self.size = max(1, int(size))
        self.tint = float(tint)
        # No ``self.image = self._paint()`` here. `FxParticle.__init__` paints,
        # and it was painting a second time: this class set the image, then
        # handed the same arguments straight back and let the base do it again.
        # Two surfaces of one to three pixels, allocated and thrown away for
        # every grain, and the grains are the most numerous particle in the
        # plane -- a landing spends fourteen and a walk spends three every tenth
        # of a second. It was invisible from here, because the second surface is
        # byte-identical and nobody looks at which of the two they got.
        super().__init__(pos, DustGrain.TTL)
        self.velocity = Vector2(velocity)

    def _paint(self) -> pygame.Surface:
        return _grain_surface(self.size, self.tint)


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

    Painted per *layout* rather than per break, in steps, out of a table keyed
    on the seed and the side. The geometry is 81 arc strokes across three steps
    and it used to be rebuilt for every single break, off a seed drawn per
    spawn from 65 536 values -- which measured at 1.14 ms of painting on a frame
    with a 16.7 ms budget, which is the single largest frame operation in the
    project and the only one close to a limit. Six times a second in a long
    parry chain, it was a hitch and not a cost.

    Nothing here is redrawn per tick, and the ladder is shared the way the dust
    ladders are: the first break of each layout pays, the rest are references.
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
        # Which layout, not which draw. The modulo is what bounds the session's
        # table, and it is why a caller may hand this any integer at all: the
        # spawner draws a fresh one from the FX stream on every break and gets
        # one of SHARD_SEEDS layouts back, so the variety a player sees is
        # unchanged and the geometry is not rebuilt.
        self.seed = int(seed) % max(1, FxGuard.SHARD_SEEDS)
        self.steps = shard_frames(self.side, self.seed)
        super().__init__(pos, ttl)
        self.image = self.steps[0]

    def _paint(self) -> pygame.Surface:
        return self.steps[0]

    def _integrate(self, delta_time: float) -> None:
        self.image = self.steps[spread_step(self.life, len(self.steps), FxGuard.SHARD_STEP_OPENS)]


_shard_cache: dict[tuple[int, int], list[pygame.Surface]] = {}
"""The break geometry, keyed on ``(side, layout)``.

    The same bound the dust ladders use, for the same reason and with the same
    consequence: the key is drawn from a finite grid, so the table can never
    outgrow it however many breaks go through it. An unbounded cache keyed on a
    per-spawn seed would be a session-long leak of the plane's largest
    surfaces."""


def shard_frames(side: float, seed: int) -> list[pygame.Surface]:
    """The shared failure of the ring, in its steps, for one side and one layout."""
    key = (1 if side >= 0.0 else 0, int(seed) % max(1, FxGuard.SHARD_SEEDS))
    cached = _shard_cache.get(key)
    if cached is not None:
        return cached
    ladder = [
        _shatter_step(index / (FxGuard.SHARD_STEPS - 1), key[1], key[0] == 1)
        for index in range(FxGuard.SHARD_STEPS)
    ]
    _shard_cache[key] = ladder
    return ladder


def _shard_fragment(
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


def _shatter_step(progress: float, seed: int, facing_right: bool) -> pygame.Surface:
    """The ring at one moment of its failure, ``progress`` from 0 to 1.

    Module-level and keyed off its own arguments, rather than a method reading
    ``self``: this is what makes the ladder above possible. As a method it had
    no identity to key on but the particle, which is to say it was unpaintable
    by construction.
    """
    radius = snap(FxGuard.SHARD_RADIUS)
    # Radius plus the furthest a piece can travel, or the circle is drawn
    # off the edge of its own surface.
    reach = snap(radius * (1.0 + FxGuard.SHARD_SPREAD * (1.0 + FxGuard.SHARD_WOUND_PUSH)))
    span = 2 * (reach + FxGuard.SHARD_MARGIN)
    surface = pygame.Surface((span, span), pygame.SRCALPHA)
    middle = span / 2.0
    rng = random.Random(seed * 977 + FxGuard.SHARD_PIECES)
    facing = 0.0 if facing_right else 180.0
    spread = FxGuard.SHARD_SPREAD * progress

    slot = 360.0 / FxGuard.SHARD_PIECES
    for index in range(FxGuard.SHARD_PIECES):
        centre = facing + index * slot + slot / 2.0
        on_wound = _angle_near(centre, facing, FxGuard.SHARD_WOUND)
        thrown = (
            spread * (1.0 + FxGuard.SHARD_WOUND_PUSH * on_wound) * rng.uniform(*FxGuard.SHARD_DRIFT)
        )
        _shard_fragment(
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
        thrown = spread * (1.0 + FxGuard.SHARD_WOUND_PUSH) * rng.uniform(*FxGuard.SHARD_KICK_DRIFT)
        _shard_fragment(
            surface,
            middle,
            centre,
            piece / 2.0 * (1.0 - FxGuard.SHARD_SHRINK * 1.3 * progress),
            radius + radius * thrown,
            FXColors.break_core,
        )
    return surface


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


def _grain_surface(size: int, tint: float) -> pygame.Surface:
    """One speck, on a surface cut exactly to it.

    No ink and no rim, on two counts. A rim around a two-pixel square is three
    pixels of edge and one of mass, so the mark becomes the outline rather than
    the dust; and the grains are the shadowed debris a kick scatters, so they
    are drawn off ``dust_grain`` and never lifted above the sheet's own body
    tone -- a field of highlights is glitter, and glitter is what a parry is
    for.
    """
    side = max(1, int(size))
    surface = pygame.Surface((side, side), pygame.SRCALPHA)
    speck(surface, _shade(FXColors.dust_grain, tint), (side // 2, side // 2), side)
    return surface


_SHEET_SEED = 0x5EED
"""The seed the mote layouts are drawn from.

Its own constant rather than the FX stream's: these layouts are shapes, and
the ladder hands the same one to every puff of a size for the whole session.
Drawing them from a live stream would make a fan's members differ between two
landings, which the eye reads as the game shaking.
"""


_puff_cache: dict[tuple[int, float, int], list[pygame.Surface]] = {}
_dash_cache: dict[tuple[int, float, int], list[pygame.Surface]] = {}

_vortex_cache: list[pygame.Surface] = []
_PUFF_MOTES: dict[int, Motes] = {}
_DASH_MOTES: dict[int, Motes] = {}
"""The lobe layouts, memoized per variant.

A layout is a fixed list of shares, so there is one per variant and never more
-- where the old ladder held a list of four large discs written out in
settings, and every size bucket re-expressed it.
"""


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


def _puff_step(radius: float, step: int, tint: float, variant: int) -> pygame.Surface:
    """One step of the sheet: the cloud at its size for this step.

    Drawn at the radius it has *become* rather than the one it started at, so
    the ladder is the growth. The first step is flattened because that is the
    shape dust has while it is still leaving the floor, and the flatten relaxes
    to nothing over the ladder.
    """
    opened = 1.0 + Dust.PUFF_GROWTH * step
    reach = radius * opened
    squash = 1.0 - (1.0 - Dust.PUFF_SQUASH) * max(0.0, 1.0 - step)
    motes = _puff_motes(variant)
    half_w, half_h = _span(motes, reach, squash)
    surface = pygame.Surface((2 * half_w, 2 * half_h), pygame.SRCALPHA)
    shape_shaded(
        surface,
        (half_w, half_h),
        _sheet_shape(motes, reach, squash),
        _shade(FXColors.dust, tint),
        _shade(FXColors.dust_lit, tint),
        _shade(FXColors.dust_deep, tint),
        _shade(FXColors.dust_shade, tint),
    )
    return surface


def _puff_motes(variant: int) -> Motes:
    """The landing sheet's lobe layout, as shares of a unit radius.

    Cached per variant, because it is the same list scaled once per step of
    every ladder that uses it, and a layout built from a fresh draw each time
    would make two puffs of one size and one tone differ for no reason.

    Seeded off the variant rather than off the FX stream on purpose: this is
    a shape, and a shape that changed between two landings would read as the
    game jittering. The variant is the only thing allowed to change it, and it
    is an index off the fan.
    """
    cached = _PUFF_MOTES.get(variant)
    if cached is None:
        cached = _mote_band(
            Dust.PUFF_MOTES,
            Dust.PUFF_BASE_SHARE,
            Dust.PUFF_TOP_SHARE,
            Dust.PUFF_MOTE_EVERY,
            Dust.PUFF_MOTE_SPREAD,
            Dust.PUFF_MOTE_RISE,
            Dust.PUFF_MOTE_BASELINE,
            Dust.PUFF_CHIP_SHARE,
            Dust.PUFF_CHIP_SIDES,
            Dust.PUFF_CHIP_TURN,
            Dust.PUFF_CHIP_GROW,
            variant,
        )
        _PUFF_MOTES[variant] = cached
    return cached


def _dash_motes(variant: int) -> Motes:
    """The trail sheet's lobe layout, as shares of a unit radius."""
    cached = _DASH_MOTES.get(variant)
    if cached is None:
        cached = _mote_band(
            DashDust.MOTES,
            DashDust.BASE_SHARE,
            DashDust.TOP_SHARE,
            DashDust.MOTE_EVERY,
            DashDust.MOTE_SPREAD,
            DashDust.MOTE_RISE,
            DashDust.MOTE_BASELINE,
            DashDust.CHIP_SHARE,
            DashDust.CHIP_SIDES,
            DashDust.CHIP_TURN,
            DashDust.CHIP_GROW,
            variant,
        )
        _DASH_MOTES[variant] = cached
    return cached


def _mote_band(
    count: int,
    base_share: tuple[float, float],
    top_share: tuple[float, float],
    every: int,
    spread: float,
    rise: tuple[float, float],
    baseline: float,
    chip_share: float,
    chip_sides: tuple[int, int],
    chip_turn: float,
    chip_grow: float,
    variant: int,
) -> Motes:
    """The sheet's parts, as shares of a unit radius, split by kind.

    Returns discs and chips separately because the caller unions them into one
    shape -- :func:`mote_shape` takes both lists, and the two kinds only differ
    in how their outline is built, not in where they sit or how big they are.

    Two strata, and the split between them is the whole *mass*. The *base* is
    the lower band: large, close together, and drawn low enough to touch, so it
    merges into one connected form. The *fringe* sits above it: smaller, and
    spread across a range of heights wider than a lobe is tall, so it overlaps
    the base in places and stands clear of it in others. That alternation is
    the notch, and the notch is what stops the silhouette being one smooth
    convex outline -- which is all four of the large discs the puff used to be
    ever summed up to, whatever the discs were offset by.

    Drawing both strata from one distribution fails, and not subtly. The height
    spread that gives the top its notches is the same spread that pulls the
    bottom lobes out of each other's reach, and the sheet comes out as a row of
    separate puffs hanging in the air. So the base is given its own, much
    tighter, band of heights and the fringe is free to scatter.

    Which of the two kinds a lobe is drawn as is the ``chip_share`` draw, and
    it is the difference between a heap of beads and a heap of gravel. There is
    no pattern in it -- an every-``n`` stride was tried and reads as corduroy
    along the bottom -- so it comes off the stream, seeded by the variant like
    everything else in the layout.

    A chip is then drawn ``chip_grow`` times larger than the disc it replaced,
    because a polygon covers less than the circle inscribed in the same radius
    and the share is drawn on the same numbers. Swapping part for part at one
    radius does not square the band, it thins it.

    Unit-radius shares, so one layout serves every size on the ladder and the
    shape scales with the puff rather than being re-drawn at each of them.
    """
    rng = random.Random(_SHEET_SEED + variant * 1021)
    base_count = max(1, count // 2 + 1)
    low, high = rise
    least, most = chip_sides
    turn = 2.0 * math.pi * max(0.0, chip_turn)
    discs: list[tuple[float, float, float]] = []
    chips: list[tuple[float, float, float, int, float]] = []
    for index in range(count):
        along = (index + 0.5) / count
        # Stratified across the band and then jittered within a slot, so the
        # sheet is always full width -- a plain draw would leave its ends thin
        # and make half the puffs in a fan smaller than the rest.
        x = spread * (2.0 * along - 1.0) + spread * rng.uniform(-0.7, 0.7) / count
        if index < base_count:
            share = rng.uniform(*base_share)
            # A lobe's own thickness, not a share of the rise band: the base
            # has to be able to touch itself at this spread, and borrowing the
            # fringe's range is the one number that stops it. It straddles the
            # band's floor rather than sitting on it, which is what notches the
            # *bottom* edge too -- the shadow pass fills the gaps between parts
            # drawn at one height, so a base band with a single height is a
            # smooth curve along the floor whichever way its top is cut.
            lift = rng.uniform(-0.07, 0.18)
        else:
            above = index - base_count
            share = top_share[1] if above % every == 0 else rng.uniform(*top_share)
            lift = rng.uniform(low, high)
        # Screen y grows downward, so a part sitting above the floor is the
        # smaller y. Hence the subtraction.
        y = baseline - lift
        if rng.random() < chip_share:
            chips.append(
                (
                    x,
                    y,
                    share * chip_grow,
                    rng.randint(least, most),
                    rng.uniform(0.0, turn),
                )
            )
        else:
            discs.append((x, y, share))
    return tuple(discs), tuple(chips)


type Motes = tuple[
    tuple[tuple[float, float, float], ...],
    tuple[tuple[float, float, float, int, float], ...],
]
"""A sheet's parts in shares of a unit radius: the discs, then the chips.

    The two kinds are kept apart because they are only different ways of
    building the same outline -- one arc by one arc, one edge by one edge --
    and nothing about where a part sits or how big it is depends on which it
    happens to be."""


_SHEET_SEED = 0x5EED
"""The seed the mote layouts are drawn from.

Its own constant rather than the FX stream's: these layouts are shapes, and
the ladder hands the same one to every puff of a size for the whole session.
Drawing them from a live stream would make a fan's members differ between two
landings, which the eye reads as the game shaking.
"""


def _sheet_shape(
    motes: Motes,
    reach: float,
    squash: float,
) -> ShapeAt:
    """The sheet's shape, rebuilt at any centre.

    The scaling happens once, here, rather than inside the four passes
    :func:`shape_shaded` makes -- so the ladder pays for it per step and not
    per pass, and so a lobe's radius and its height are multiplied by the same
    ``reach``, which is what keeps a part circular while the sheet it belongs
    to is squashed.
    """
    discs = tuple((x * reach, y * reach * squash, size * reach) for x, y, size in motes[0])
    chips = tuple(
        (x * reach, y * reach * squash, size * reach, sides, heading)
        for x, y, size, sides, heading in motes[1]
    )

    def shape_at(centre: tuple[float, float]) -> Shape:
        return mote_shape(centre, discs, chips)

    return shape_at


def _span(motes: Motes, reach: float, squash: float) -> tuple[int, int]:
    """The half-width and half-height a sheet of parts needs, as whole pixels.

    Per axis, because a sheet of dust is about twice as wide as it is tall and
    a square cut for it wastes most of what it allocates. The cut has to hold
    the widest part on each axis -- its offset plus its own radius -- and a
    spare pixel for the rim outside the silhouette and the shadow under it.

    Cutting to the nominal radius instead is what the old margins did, and they
    cut the landing puffs a surface nearly five times the size of the cloud
    drawn on it.
    """
    parts = [
        (x * reach, y * reach * squash, size * reach)
        for x, y, size in (*motes[0], *(part[:3] for part in motes[1]))
    ]
    across = snap(max((abs(x) + size for x, _, size in parts), default=1.0))
    down = snap(max((abs(y) + size for _, y, size in parts), default=1.0))
    return across + 2, down + 2


def puff_tint(index: int) -> float:
    """The body tone the puff at ``index`` in a fan is drawn in.

    Cycled rather than drawn, because the ladder is keyed on tone as well as
    radius: a fan of four sheets in four identical greys reads as a stamped
    pattern, and a row of near-identical tones is what a spot-on-the-eye
    randomiser would give. Indexed modulo the palette, so the caller can hand
    it the puff index directly.
    """
    tints = _puff_tints()
    return tints[index % len(tints)]


def puff_variant(index: int) -> int:
    """The silhouette the puff at ``index`` in a fan is drawn from.

    Offset from the tone's own palette rather than indexed alongside it, so
    that a tone and a shape can never pair up twice: with the same index for
    both, a fan of four would walk the diagonals of a four-by-four grid and
    land on ``(0,0) (1,1) (2,2) (3,3)`` -- four members matching on tone, four
    matching on shape, and a fan that looks like a diagonal.
    """
    return (index + 1) % max(1, Dust.PUFF_VARIANTS)


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


def puff_frames(radius: float, tint: float = 0.0, variant: int = 0) -> list[pygame.Surface]:
    """The shared billow of every puff of about ``radius``, in one body tone.

    A puff animates by stepping a ladder rather than by redrawing its cloud,
    and the ladder is keyed on the discrete radii in ``Dust.PUFF_BUCKETS``,
    the discrete tones in ``Dust.PUFF_TINT`` and the discrete silhouettes in
    ``Dust.PUFF_VARIANTS``, built once per session. That is what makes a fan
    of four affordable: four puffs of similar size, tone and shape are
    references into the same rows, not four sets of surfaces allocated at the
    moment of landing.

    A continuous radius would mean a surface per particle, which is the
    allocation ``notes/refacto.md`` already flags as the FX plane's main
    remaining cost, and a landing is exactly when four of them happen at once.
    A display format change invalidates the cache along with everything else.
    """
    key = (_puff_bucket(radius), round(tint, 3), variant % max(1, Dust.PUFF_VARIANTS))
    cached = _puff_cache.get(key)
    if cached is not None:
        return cached
    ladder = [_puff_step(key[0], step, tint, key[2]) for step in range(Dust.PUFF_STEPS)]
    _puff_cache[key] = ladder
    return ladder


def _dash_step(radius: float, step: int, tint: float, variant: int) -> pygame.Surface:
    """One step of the trail: the sheet at its size for this step.

    The landing sheet's step with the dark side dropped: no rim and no
    shadow, so it carries the lit edge and the body and nothing else. The block
    gave its rim up for the same reason and the landing sheet's argument
    applies unchanged -- the trail hangs on open air, where an outline is a
    grey edge drawn around a light mark, and where a shadow underneath a
    puff-less mark is a shape floating over nothing.

    What is left is the arrangement that does the work: many small lobes rather
    than a few large ones, so the silhouette is notched, and a one-pixel lit
    edge along the top of all of them rather than a disc of light inside one.
    """
    opened = 1.0 + DashDust.GROWTH * step
    reach = radius * opened
    squash = 1.0 - (1.0 - DashDust.SQUASH) * max(0.0, 1.0 - step)
    motes = _dash_motes(variant)
    half_w, half_h = _span(motes, reach, squash)
    surface = pygame.Surface((2 * half_w, 2 * half_h), pygame.SRCALPHA)
    shape_shaded(
        surface,
        (half_w, half_h),
        _sheet_shape(motes, reach, squash),
        _shade(FXColors.dust, tint),
        _shade(FXColors.dust_lit, tint),
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


def footstep_tint(index: int, foot: bool) -> float:
    """The body tone for one half of one footstep.

    Discrete, drawn from :func:`_footstep_tints`, because the ladder is keyed on
    the tone it is handed, rounded to three places, so a *continuously* sampled
    tone misses the cache on every spawn and paints four surfaces to replace one.
    See ``FootstepDust.TONES`` for what that cost before it was fixed.

    Indexed by the within-step slot *and* by which foot laid it, which is what
    keeps a comb from being a row of identical marks. ``index`` alone would hand
    every step in the game the same two tones -- the same pair repeated for as
    long as the player holds a direction -- and the foot alternates for free,
    since the emitter is already carrying which one this is. Two feet against
    four tones is two pairs, swapping as the steps alternate.
    """
    tones = _footstep_tints()
    offset = 0 if foot else len(tones) // 2
    return tones[(index + offset) % len(tones)]


def _footstep_tints() -> tuple[float, ...]:
    """The body shifts a footstep is drawn from, across ``FootstepDust.TINT``.

    The landing fan's own builder, for the same reason it is discrete: a tone
    costs a cached row instead of a surface per particle.

    Built per call rather than memoized, which is what its two neighbours do and
    what the saving is worth: this is four pieces of arithmetic, twenty times a
    second, and a memo over it measured at nineteen microseconds per second --
    nothing against the ladder it exists to feed. It would also have been the
    only mutable piece of module state in the file, and a stale one would
    quietly ignore a changed ``FootstepDust.TINT``.
    """
    low, high = FootstepDust.TINT
    count = max(1, FootstepDust.TONES)
    if count < 2:
        return (low,)
    span = high - low
    return tuple(low + span * i / (count - 1) for i in range(count))


def dash_variant(index: int, count: int) -> int:
    """The silhouette the trail puff at ``index`` of ``count`` is drawn from.

    A stride, not an offset like the landing fan's, and the difference is
    deliberate. A dash's ticks are laid one after another along the same 88px
    of path, and the ribbon is one continuous mark: two ticks drawn from
    different silhouettes read as two separate events on one movement. Every
    member of an emission takes its variant from the same head of the palette,
    so a tick and a burst agree on shape even though they differ in size.
    """
    return index % max(1, DashDust.VARIANTS)


def dash_frames(radius: float, tint: float = 0.0, variant: int = 0) -> list[pygame.Surface]:
    """The shared billow of every trail puff of about ``radius``, in one tone.

    The landing ladder's contract, and the reason for it applies twice over
    here. A dash lays puffs on a cadence rather than in a single fan, so there
    are more of them alive at once, and a continuous radius would mean a
    surface per particle -- exactly the allocation ``notes/refacto.md``
    flags as the plane's main remaining cost. Keyed on the discrete radii in
    ``DashDust.BUCKETS``, the discrete tones in ``DashDust.TINT`` and the
    discrete silhouettes in ``DashDust.VARIANTS``, and built once per session.

    A display format change invalidates the cache along with everything else.
    """
    key = (_dash_bucket(radius), round(tint, 3), variant % max(1, DashDust.VARIANTS))
    cached = _dash_cache.get(key)
    if cached is not None:
        return cached
    ladder = [_dash_step(key[0], step, tint, key[2]) for step in range(DashDust.STEPS)]
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
    _PUFF_MOTES.clear()
    _DASH_MOTES.clear()
    _shard_cache.clear()
    _vortex_cache = []
