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

from src.core.asset_library import shared_library
from src.core.colors import Color, Colors, FXColors
from src.core.fx.draw import (
    ALPHA_STEPS,
    disc,
    disc_shape,
    draw_arc_stroke,
    draw_inked_polygon,
    ellipse_ring,
    ink_shape,
    inked_polygon,
    life_alpha,
    life_level,
    snap,
    spread_step,
    star_shape,
    streak_points,
)
from src.core.settings import Dust, FxDash, FxDecal, FxDizzy, FxGuard, Sweat


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

    """A fading puff of dust, kicked out of the feet.

    With the shipped debris frames the puff cycles through them over its
    life; without them, as on a bare checkout, it falls back to a plain disc.
    Cached library frames are never mutated, so each puff scales its own
    copies once, at construction.
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
        frames: list[pygame.Surface] | None = None,
    ) -> None:
        self.radius = float(radius)
        self.frames: list[pygame.Surface] | None = None
        if frames:
            self.frames = [
                pygame.transform.scale(
                    frame,
                    (
                        max(1, int(frame.get_width() * Dust.FRAME_SCALE)),
                        max(1, int(frame.get_height() * Dust.FRAME_SCALE)),
                    ),
                )
                for frame in frames
            ]
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)
        if self.frames:
            self.image = self.frames[0].copy()
            self.rect = self.image.get_frect(center=self.pos)

    def _paint(self) -> pygame.Surface:
        side = max(2, int(self.radius * 2.0))
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        ink_shape(
            surface,
            disc_shape((side / 2.0, side / 2.0), side / 2.0 - 1.0),
            FXColors.dust,
            FXColors.dust_deep,
            1,
        )
        return surface

    def _integrate(self, delta_time: float) -> None:
        super()._integrate(delta_time)
        if self.frames:
            self.image = self.frames[min(int(self.life * len(self.frames)), len(self.frames) - 1)]


class StreakParticle(FxParticle):
    family: ClassVar[str] = "dash_streak"

    """A speed line: a thin taper lying along the velocity, gone in a blink.

    Solid dark ink and no rim, which is the opposite of every other shape
    here. A one-pixel ink rim around a three-pixel line is most of the line,
    and the result reads as a worm; the level's sky is light, so a dark taper
    is also the one that carries.
    """

    fade_in: ClassVar[float] = FxDash.STREAK_FADE_IN

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        length: float = 24.0,
        ttl: float = FxDash.STREAK_TTL,
        thickness: float = FxDash.STREAK_THICKNESS,
    ) -> None:
        self.length = float(length)
        self.thickness = float(thickness)
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)

    def _paint(self) -> pygame.Surface:
        heading = math.atan2(self.velocity.y, self.velocity.x)
        return inked_polygon(
            streak_points((0, 0), self.length, self.thickness, heading),
            FXColors.ink_cool,
            FXColors.ink_cool,
            0,
        )


class DashBurstPuff(DustParticle):
    """The puff a dash throws backward.

    The same shape as a landing dust puff, spent from a different budget: a
    dash and a landing can happen on the same tick, and one must not spend
    the room the other needs.
    """

    family: ClassVar[str] = "dash_burst"


class WindLine(StreakParticle):
    """A speed line torn off ahead of a dash.

    The same shape as a trailing streak, spent from a different budget so a
    long dash cannot fill the plane with its own wind.
    """

    family: ClassVar[str] = "dash_wind"


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


class DashShockwaveParticle(FxParticle):
    family: ClassVar[str] = "dash_shockwave"

    """A ring on the ground at dash start.

    The ring is drawn once, at full size, then shown through four pre-scaled
    steps: growing it meant redrawing it at a new radius every frame, and the
    ellipse is what makes it read as lying on the floor rather than standing
    around the character.
    """

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        ttl: float = FxDash.SHOCKWAVE_TTL,
    ) -> None:
        self.steps = _shockwave_steps()
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        return self.steps[0]

    def _integrate(self, delta_time: float) -> None:
        spread = 1.0 - (1.0 - self.life) ** 2
        self.image = self.steps[min(int(spread * len(self.steps)), len(self.steps) - 1)]


class ImpactDecalParticle(FxParticle):
    family: ClassVar[str] = "impact_decal"

    """A mark left on the ground where a hard landing happened.

    Still, short-lived, and behind the moving plane: the puffs say how hard
    the landing was, this says where.
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
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        side = snap(self.width) * 2 + FxDecal.MARGIN
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        middle = (side / 2.0, side / 2.0)
        for heading, scale in FxDecal.LOBES:
            draw_inked_polygon(
                surface,
                streak_points(
                    (0, 0),
                    self.width * scale,
                    FxDecal.THICKNESS,
                    heading,
                    FxDecal.CURVE,
                ),
                FXColors.decal,
                FXColors.decal_ink,
                1,
                at=middle,
            )
        return surface


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


_shockwave_cache: list[pygame.Surface] = []


def _shockwave_steps() -> list[pygame.Surface]:
    """The dash ring at five sizes, built once and shared.

    Redrawn per step rather than scaled from one image, so the rim can thin
    out as the ring grows: scaling a fat ring up makes a heavier ring, and a
    shockwave is defined by getting lighter as it spreads.
    """
    global _shockwave_cache
    if _shockwave_cache:
        return _shockwave_cache
    steps: list[pygame.Surface] = []
    for index in range(FxDash.SHOCKWAVE_STEPS):
        spread = index / max(1, FxDash.SHOCKWAVE_STEPS - 1)
        first, each = FxDash.SHOCKWAVE_SCALE
        scale = first + each * spread
        rx = FxDash.SHOCKWAVE_RADIUS * scale
        ry = rx * FxDash.SHOCKWAVE_SQUASH
        thick, thin = FxDash.SHOCKWAVE_RIM
        rim = max(1, round(thick + (thin - thick) * spread))
        wide = snap(rx) * 2 + rim + FxDash.SHOCKWAVE_MARGIN
        flat = snap(ry) * 2 + rim + FxDash.SHOCKWAVE_MARGIN
        surface = pygame.Surface((wide, flat), pygame.SRCALPHA)
        middle = (wide / 2.0, flat / 2.0)
        ellipse_ring(surface, FXColors.shockwave_ink, middle, rx, ry, rim)
        if rim > 1:
            ellipse_ring(
                surface,
                FXColors.shockwave,
                middle,
                max(1.0, rx - rim / 2.0),
                max(0.5, ry - rim / 2.0),
                max(1, rim - 2),
            )
        steps.append(surface)
    _shockwave_cache = steps
    return steps


_frames_cache: list[pygame.Surface] | None = None
_frames_miss = False
_vortex_cache: list[pygame.Surface] = []


def particle_frames() -> list[pygame.Surface] | None:
    """The shipped debris strip, or None on a bare checkout.

    Memoized, and so is the miss: the library caches converted frames, and a
    checkout with no ``assets/`` tree would otherwise re-raise on every call.
    """
    global _frames_cache, _frames_miss
    if _frames_cache is not None:
        return _frames_cache
    if _frames_miss:
        return None
    try:
        _frames_cache = shared_library().frames(Dust.FRAMES_DIR)
        return _frames_cache
    except FileNotFoundError:
        _frames_miss = True
        return None


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
    """Forget the memoized frames, the misses, and the procedural ladders.

    A display format change (``pygame.display.set_mode``) invalidates every
    converted surface, so this cache layer has to be dropped with
    ``AssetLibrary`` or it would keep handing back stale ones.
    """
    global _frames_cache, _frames_miss, _vortex_cache, _shockwave_cache
    _frames_cache = None
    _frames_miss = False
    _vortex_cache = []
    _shockwave_cache = []
