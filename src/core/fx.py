"""Render-only impact FX: dust, speed lines, sparks, stars and impact rings.

Dust lives in ``groups.fx_sprites`` (no collision, no damage): it is
integrated by :class:`PhysicsSystem`, drawn by :class:`Renderer` like any
visible sprite, and deliberately excluded from rollback snapshots and
golden digests -- pure juice, zero simulation impact.

The look, in one sentence: whole pixels, dark ink rims, and alpha that moves
in discrete steps, because the game is magnified with nearest-neighbour
scaling and a soft particle turns to mush at that magnification. Every shape
comes from :mod:`src.core.rendering.fx_draw`, which is where those rules
live.

Which particles rebuild their surface
-------------------------------------
A particle that redraws its pixels every frame pays for a drawing, not for an
allocation, so the only question is whether its *look* changes. Two of them
used to, and both stopped: the shockwave is drawn once at full size and shown
through a few pre-scaled steps, and the dizzy swirl is a shared ladder of
rotation steps. Everything here builds its surface at construction and then
only moves or fades, which is what ``tests/unit/test_fx_surfaces.py`` pins.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, ClassVar

import pygame
from pygame.math import Vector2

from src.core.colors import Color, Colors, FXColors
from src.core.rendering.fx_draw import (
    ALPHA_STEPS,
    disc,
    disc_shape,
    draw_inked_polygon,
    ellipse_ring,
    ink_shape,
    inked_polygon,
    life_alpha,
    life_level,
    polygon_bounds,
    ring,
    snap,
    star_shape,
    streak_points,
)
from src.core.settings import Dust, Sweat

__all__ = [
    "BurstSpec",
    "DashShockwaveParticle",
    "DashTrailParticle",
    "DizzyVortexParticle",
    "DustParticle",
    "FxParticle",
    "ShieldArcParticle",
    "ImpactDecalParticle",
    "OrbitParticle",
    "SparkParticle",
    "StreakParticle",
    "SweatParticle",
    "clear_frame_cache",
    "dash_direction",
    "facing_side",
    "iter_landing_entities",
    "particle_frames",
    "spawn_break_burst",
    "spawn_dash_burst",
    "spawn_dash_shockwave",
    "spawn_dash_streak",
    "spawn_dash_trail",
    "spawn_dash_wind",
    "spawn_dizzy_stars",
    "spawn_dizzy_vortex",
    "spawn_guard_arc",
    "spawn_impact_decal",
    "spawn_landing_dust",
    "spawn_sweat_drops",
    "vortex_frames",
]

SPARK_TTL = 0.3
SPARK_GRAVITY = 900.0
SPARK_SIZE = 4.0
BREAK_SPARK_COUNT = 12
DIZZY_STAR_COUNT = 6
DIZZY_STAR_COLORS: tuple[Color, ...] = (FXColors.star, FXColors.star_core, Colors.gold)
DIZZY_STAR_RADIUS = 26.0
DIZZY_STAR_SPEED = 2.4
DIZZY_STAR_TTL = 1.2
DIZZY_STAR_SPAWN_EVERY = 0.5
DIZZY_STAR_BATCH = 2
DUST_RADIUS = 5.0
DUST_RISE = -60.0
DUST_DRAG = 4.0
DASH_BURST_COUNT = 10
DASH_WIND_LINES = 2
MAX_FX_SPRITES = 64
FX_FAMILY_BUDGETS: dict[str, int] = {
    "dizzy_star": 8,
    "dash_trail": 26,
    "dash_wind": 12,
    "dizzy_vortex": 8,
    "impact_decal": 8,
}
"""Per-family caps, on top of :data:`MAX_FX_SPRITES`.

The global cap alone lets a fourteen-spark parry starve the dash trail, so a
fighter who has just parried stops seeing their own dash. These reserve room
for the effects that have to keep animating.
"""
PARTICLE_FRAMES_DIR = "assets/graphics/effects/particle"
PARTICLE_FRAME_SCALE = 2.0
STREAK_TTL = 0.22
STREAK_THICKNESS = 3.0
WIND_THICKNESS = 2.0
SWEAT_OUTLINE_WIDTH = 2
SWEAT_RADIUS = 5.0
SWEAT_MARGIN = 2
SWEAT_POP_UP = -110.0
SWEAT_GRAVITY = 620.0
SWEAT_SPREAD = 0.12
DIZZY_VORTEX_TTL = 0.5
DIZZY_VORTEX_SPAWN_EVERY = 0.12
DIZZY_VORTEX_RADIUS = 16.0
DIZZY_VORTEX_FRAMES = 6
DIZZY_VORTEX_ARMS = 3
DASH_SHOCKWAVE_RADIUS = 44.0
DASH_SHOCKWAVE_TTL = 0.18
DASH_SHOCKWAVE_STEPS = 5
DASH_TRAIL_LENGTH = 35.0
DASH_TRAIL_WIDTH = 6.0
DASH_TRAIL_TTL = 0.15
DASH_TRAIL_SPAWN_EVERY = 0.015
DECAL_RADIUS = 22.0
DECAL_TTL = 0.28
SHIELD_ARC_RADIUS = 20.0
SHIELD_ARC_TTL = 0.22
SHIELD_ARC_RIM = 5
"""Ring thickness in world units; the lit ring sits inside the ink one."""


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
    family: str = ""
    """The budget a particle draws against, if any."""

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
    """A fading puff of dust, kicked out of the feet.

    With the shipped debris frames the puff cycles through them over its
    life; without them, as on a bare checkout, it falls back to a plain disc.
    Cached library frames are never mutated, so each puff scales its own
    copies once, at construction.
    """

    gravity: ClassVar[float] = DUST_RISE
    drag: ClassVar[float] = DUST_DRAG
    fade_in: ClassVar[float] = 0.15
    behind: ClassVar[bool] = True

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = Dust.TTL,
        radius: float = DUST_RADIUS,
        frames: list[pygame.Surface] | None = None,
    ) -> None:
        self.radius = float(radius)
        self.frames: list[pygame.Surface] | None = None
        if frames:
            self.frames = [
                pygame.transform.scale(
                    frame,
                    (
                        max(1, int(frame.get_width() * PARTICLE_FRAME_SCALE)),
                        max(1, int(frame.get_height() * PARTICLE_FRAME_SCALE)),
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
    """A speed line: a thin taper lying along the velocity, gone in a blink.

    Solid dark ink and no rim, which is the opposite of every other shape
    here. A one-pixel ink rim around a three-pixel line is most of the line,
    and the result reads as a worm; the level's sky is light, so a dark taper
    is also the one that carries.
    """

    fade_in: ClassVar[float] = 0.2

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        length: float = 24.0,
        ttl: float = STREAK_TTL,
        thickness: float = STREAK_THICKNESS,
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


class SparkParticle(FxParticle):
    """A heavy shard thrown out of a broken guard.

    The only thrown particle left in the game. Blocks are a ring and a parry
    is the same ring in gold, so nothing flies out of a block any more, and a
    break -- rare, loud, and about a guard that failed -- is the one event
    that can afford a burst.
    """

    gravity: ClassVar[float] = SPARK_GRAVITY
    fade_in: ClassVar[float] = 0.12

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        color: Color,
        ttl: float = SPARK_TTL,
        size: float = SPARK_SIZE,
        core: Color | None = None,
        elongation: float = 1.0,
        ink: Color = FXColors.ink,
    ) -> None:
        self.color = color
        self.core = core if core is not None else color
        self.size = float(size)
        self.elongation = max(1.0, float(elongation))
        self.ink = ink
        self.family = "break_burst"
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)

    def _paint(self) -> pygame.Surface:
        return self._shard()

    def _shard(self) -> pygame.Surface:
        """A heavy triangle: three points, a fat waist, inked."""
        reach = snap(self.size * self.elongation) * 2 + 6
        surface = pygame.Surface((reach, reach), pygame.SRCALPHA)
        middle = (reach / 2.0, reach / 2.0)
        heading = math.atan2(self.velocity.y, self.velocity.x)
        ink_shape(
            surface,
            star_shape(middle, self.size * self.elongation, self.size * 0.62, 3, heading),
            self.color,
            self.ink,
            1,
        )
        ink_shape(
            surface,
            star_shape(middle, self.size * 0.5, self.size * 0.3, 3, heading),
            self.core,
            self.color,
            0,
        )
        return surface


class OrbitParticle(FxParticle):
    """A star circling a point, for as long as the stun lasts.

    It orbits rather than falls. The dizzy stars used to be ordinary sparks,
    so the gravity that reads well on a spark dragged the whole constellation
    through the floor over the course of a long stun. The position is a
    function of the elapsed time, which makes the movement exactly
    reproducible and costs no integration.
    """

    fade_in: ClassVar[float] = 0.08

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
        self.family = "dizzy_star"
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
    """A purple swirl at the feet of a dizzy entity.

    The swirl is a shared ladder of rotation steps: it used to redraw three
    arms of three polygons per particle per frame, and a stun puts up to four
    of them on screen at once.
    """

    fade_in: ClassVar[float] = 0.1

    def __init__(self, pos: tuple[float, float] | Vector2, ttl: float = DIZZY_VORTEX_TTL) -> None:
        self.family = "dizzy_vortex"
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        return vortex_frames()[0]

    def _integrate(self, delta_time: float) -> None:
        self.image = vortex_frames()[life_level(self.life, 0.0, DIZZY_VORTEX_FRAMES)]


class DashShockwaveParticle(FxParticle):
    """A ring on the ground at dash start.

    The ring is drawn once, at full size, then shown through four pre-scaled
    steps: growing it meant redrawing it at a new radius every frame, and the
    ellipse is what makes it read as lying on the floor rather than standing
    around the character.
    """

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        ttl: float = DASH_SHOCKWAVE_TTL,
    ) -> None:
        self.steps = _shockwave_steps()
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        return self.steps[0]

    def _integrate(self, delta_time: float) -> None:
        spread = 1.0 - (1.0 - self.life) ** 2
        self.image = self.steps[min(int(spread * len(self.steps)), len(self.steps) - 1)]


class DashTrailParticle(FxParticle):
    """A curved streak left along the dash path.

    Built once, and only faded: the shape is a function of the direction and
    three constants fixed at construction, so redrawing it per frame produced
    the same pixels every time.
    """

    fade_in: ClassVar[float] = 0.1

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        direction: float,
        ttl: float = DASH_TRAIL_TTL,
        curve: float = 6.0,
        length: float = DASH_TRAIL_LENGTH,
        width: float = DASH_TRAIL_WIDTH,
    ) -> None:
        self.direction = direction
        self.curve = float(curve)
        self.length = float(length)
        self.width = float(width)
        self.family = "dash_trail"
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        heading = 0.0 if self.direction >= 0.0 else math.pi
        body = streak_points((0, 0), self.length, self.width, heading, self.curve)
        core = streak_points(
            (0, 0), self.length * 0.8, max(1.0, self.width * 0.34), heading, self.curve
        )
        left, top, width, height = polygon_bounds([*body, *core])
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        at = (-left, -top)
        draw_inked_polygon(surface, body, FXColors.trail_ink, FXColors.trail_ink, 0, at=at)
        draw_inked_polygon(surface, core, FXColors.trail, FXColors.trail, 0, at=at)
        return surface


class ImpactDecalParticle(FxParticle):
    """A mark left on the ground where a hard landing happened.

    Still, short-lived, and behind the moving plane: the puffs say how hard
    the landing was, this says where.
    """

    behind: ClassVar[bool] = True
    fade_in: ClassVar[float] = 0.05

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        ttl: float = DECAL_TTL,
        width: float = DECAL_RADIUS,
    ) -> None:
        self.width = float(width)
        self.family = "impact_decal"
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        side = snap(self.width) * 2 + 6
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        middle = (side / 2.0, side / 2.0)
        tongues = ((0.0, 1.0), (2.1, 0.7), (4.2, 0.55))
        for heading, scale in tongues:
            draw_inked_polygon(
                surface,
                streak_points((0, 0), self.width * scale, 5.0, heading, 0.0),
                FXColors.decal,
                FXColors.decal_ink,
                1,
                at=middle,
            )
        return surface


class ShieldArcParticle(FxParticle):
    """A segmented guard arc on the side the block came from.

    The block's whole silhouette: one arc, in front of the guard, facing the
    attacker. It reads as a shield taking the hit because it has a direction
    and stays in one place, where a fan of thrown particles reads as an
    explosion inside the fighter.
    """

    fade_in: ClassVar[float] = 0.08

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        side: float,
        parried: bool = False,
        ttl: float = SHIELD_ARC_TTL,
    ) -> None:
        self.side = 1.0 if side >= 0.0 else -1.0
        self.body = FXColors.parry_spark if parried else FXColors.shield_arc
        self.rim = FXColors.ink_warm if parried else FXColors.shield_ink
        self.parried = parried
        self.family = "shield_arc"
        super().__init__(pos, ttl)

    def _paint(self) -> pygame.Surface:
        """An ink ring and a lit ring inside it, concentric.

        Drawn as circles rather than arcs on purpose: ``pygame.draw.arc``
        ignores its start and stop angles and closes the ring whatever they
        say, so the shape this particle has always been is a full circle, and
        the segmented-arc intent was never in the picture at all.
        """
        radius = snap(SHIELD_ARC_RADIUS)
        side = 2 * radius + SHIELD_ARC_RIM + 2
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        middle = (side / 2.0, side / 2.0)
        ring(surface, self.rim, middle, radius + SHIELD_ARC_RIM / 2, SHIELD_ARC_RIM)
        ring(surface, self.body, middle, radius, SHIELD_ARC_RIM / 2)
        return surface


class SweatParticle(FxParticle):
    """A comic teardrop popped off the head of an exhausted dasher.

    Heavier than dust, so the pop is immediately fought by gravity and the
    drop traces a short nervous fountain before winking out. Fat, inked and
    glossed: it has to read as a bead of liquid at gameplay distance.
    """

    gravity: ClassVar[float] = SWEAT_GRAVITY
    fade_in: ClassVar[float] = 0.1

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = Sweat.TTL,
        radius: float = SWEAT_RADIUS,
        tint: float = 0.0,
    ) -> None:
        self.radius = float(radius)
        self.tint = float(tint)
        self.family = "sweat"
        super().__init__(pos, ttl)
        self.velocity = Vector2(velocity)

    def _paint(self) -> pygame.Surface:
        radius = int(self.radius)
        outline = SWEAT_OUTLINE_WIDTH
        margin = SWEAT_MARGIN
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
    for index in range(DASH_SHOCKWAVE_STEPS):
        scale = 0.3 + 0.7 * (index / max(1, DASH_SHOCKWAVE_STEPS - 1))
        rx = DASH_SHOCKWAVE_RADIUS * scale
        ry = rx * 0.4
        rim = max(1, round(4 - 3 * (index / max(1, DASH_SHOCKWAVE_STEPS - 1))))
        wide = snap(rx) * 2 + rim + 4
        flat = snap(ry) * 2 + rim + 4
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
        from src.core.asset_library import shared_library  # noqa: PLC0415 - lazy, headless-safe

        _frames_cache = shared_library().frames(PARTICLE_FRAMES_DIR)
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
    radius = DIZZY_VORTEX_RADIUS
    side = 2 * (snap(radius) + 4)
    middle = (side / 2.0, side / 2.0)
    frames: list[pygame.Surface] = []
    for step in range(DIZZY_VORTEX_FRAMES):
        turn = step * 2.0 * math.pi / DIZZY_VORTEX_FRAMES
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        for arm in range(DIZZY_VORTEX_ARMS):
            heading = turn + arm * 2.0 * math.pi / DIZZY_VORTEX_ARMS
            reach = radius * (0.42 + 0.2 * (arm % 2))
            arm_surface = inked_polygon(
                streak_points((0, 0), reach, 3.0, heading, reach * 0.4),
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


def _puff_rng(entity: Any) -> random.Random:
    """The entity's own RNG when it has one, else a throwaway instance."""
    rng = getattr(entity, "rng", None)
    if isinstance(rng, random.Random):
        return rng
    return random.Random()


def dash_direction(entity: Any) -> float:
    """Signed dash direction: live velocity wins, facing is the fallback.

    Velocity is authoritative mid-dash (air dashes, turnarounds); facing only
    matters on the very first tick, before the dash speed kicks in.
    """
    velocity = getattr(entity, "velocity", None)
    vx = float(getattr(velocity, "x", 0.0) or 0.0)
    if abs(vx) > 1.0:
        return 1.0 if vx > 0.0 else -1.0
    return facing_side(entity)


def facing_side(entity: Any) -> float:
    """+1 when the entity faces right, -1 when it faces left."""
    return 1.0 if bool(getattr(entity, "facing_right", True)) else -1.0


def _has_room(fx_group: pygame.sprite.Group, family: str | None = None) -> bool:
    """Whether one more particle fits, under the global cap and the family one."""
    if len(fx_group) >= MAX_FX_SPRITES:
        return False
    if family is None:
        return True
    cap = FX_FAMILY_BUDGETS.get(family)
    if cap is None:
        return True
    return sum(1 for sprite in fx_group if getattr(sprite, "family", "") == family) < cap


def _landing_strength(impact: float) -> float:
    """How big a landing reads, from the fall speed that caused it."""
    return min(2.2, max(0.6, float(impact) / (Dust.MIN_FALL_SPEED * 1.6)))


def _contact_point(entity: Any, origin: tuple[float, float] | None) -> Vector2:
    """Where a spark belongs: the contact if there is one, else the leading edge."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return Vector2(origin or (0.0, 0.0))
    if origin is not None:
        return Vector2(origin)
    side = facing_side(entity)
    return Vector2(
        hitbox.centerx + side * hitbox.width * 0.5,
        hitbox.centery - hitbox.height * 0.15,
    )


def spawn_landing_dust(
    fx_group: pygame.sprite.Group,
    entity: Any,
    impact: float = Dust.MIN_FALL_SPEED,
) -> list[DustParticle]:
    """Fan ``Dust.COUNT`` puffs out of the entity's feet.

    The count is fixed and the size is not: a fall several times the threshold
    throws wider, heavier puffs, which is what makes a hard landing read as
    harder than a merely brisk one.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return []
    rng = _puff_rng(entity)
    frames = particle_frames()
    strength = _landing_strength(impact)
    puffs: list[DustParticle] = []
    for index in range(Dust.COUNT):
        side = index - (Dust.COUNT - 1) / 2.0
        velocity = (
            side * 55.0 * strength + rng.uniform(-20.0, 20.0),
            -abs(rng.uniform(60.0, 160.0)) * strength - (40.0 if index % 2 == 0 else 0.0),
        )
        puff = DustParticle(
            (hitbox.centerx + side * 4.0, hitbox.bottom - 2.0),
            velocity,
            radius=DUST_RADIUS * strength + rng.uniform(0.0, 3.0),
            frames=frames,
        )
        puff.family = "landing_dust"
        fx_group.add(puff)
        puffs.append(puff)
    return puffs


def spawn_impact_decal(
    fx_group: pygame.sprite.Group,
    entity: Any,
    impact: float = Dust.MIN_FALL_SPEED,
) -> ImpactDecalParticle | None:
    """A ground mark under a hard landing, scaled by the fall speed."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    if not _has_room(fx_group, "impact_decal"):
        return None
    decal = ImpactDecalParticle(
        (hitbox.centerx, hitbox.bottom - 1.0),
        width=DECAL_RADIUS * _landing_strength(impact),
    )
    fx_group.add(decal)
    return decal


def spawn_dash_burst(
    fx_group: pygame.sprite.Group,
    entity: Any,
    count: int = DASH_BURST_COUNT,
) -> list[DustParticle]:
    """Kick a fan of dust backward as the dash starts (rising edge only)."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None or count <= 0:
        return []
    direction = dash_direction(entity)
    rng = _puff_rng(entity)
    frames = particle_frames()
    puffs: list[DustParticle] = []
    for index in range(count):
        spread = index - (count - 1) / 2.0
        puff = DustParticle(
            (
                hitbox.centerx - direction * hitbox.width / 2.0,
                hitbox.bottom - 4.0 + spread * 3.0,
            ),
            (
                -direction * rng.uniform(140.0, 260.0),
                -abs(rng.uniform(40.0, 140.0)),
            ),
            radius=DUST_RADIUS + rng.uniform(0.0, 2.0),
            frames=frames,
        )
        puff.family = "dash_burst"
        fx_group.add(puff)
        puffs.append(puff)
    return puffs


def spawn_dash_streak(fx_group: pygame.sprite.Group, entity: Any) -> StreakParticle | None:
    """A speed line trailing the dasher: thin, fast, gone in a blink."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    direction = dash_direction(entity)
    rng = _puff_rng(entity)
    streak = StreakParticle(
        (
            hitbox.centerx - direction * rng.uniform(0.0, hitbox.width / 2.0),
            hitbox.centery + rng.uniform(-hitbox.height / 3.0, hitbox.height / 3.0),
        ),
        (-direction * rng.uniform(500.0, 800.0), 0.0),
        length=rng.uniform(18.0, 34.0),
    )
    streak.family = "dash_streak"
    fx_group.add(streak)
    return streak


def spawn_dash_wind(fx_group: pygame.sprite.Group, entity: Any) -> list[StreakParticle]:
    """Wind lines torn off ahead of the dasher, on the side it faces.

    The trail behind the dasher says where it has been; these say how fast it
    is going, and they are the only FX in the game that point forwards.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return []
    if not _has_room(fx_group, "dash_wind"):
        return []
    direction = dash_direction(entity)
    rng = _puff_rng(entity)
    pace = abs(float(getattr(getattr(entity, "velocity", None), "x", 0.0) or 0.0))
    lines: list[StreakParticle] = []
    for _ in range(DASH_WIND_LINES):
        line = StreakParticle(
            (
                hitbox.centerx + direction * hitbox.width * rng.uniform(0.3, 1.2),
                hitbox.centery + rng.uniform(-hitbox.height / 2.0, hitbox.height / 2.0),
            ),
            (-direction * (pace + rng.uniform(300.0, 700.0)), 0.0),
            length=rng.uniform(20.0, 40.0),
            thickness=WIND_THICKNESS,
        )
        line.family = "dash_wind"
        fx_group.add(line)
        lines.append(line)
    return lines


def spawn_dash_shockwave(
    fx_group: pygame.sprite.Group, entity: Any
) -> DashShockwaveParticle | None:
    """A ground ring at the entity's feet on dash start."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    if not _has_room(fx_group):
        return None
    shockwave = DashShockwaveParticle(
        (hitbox.centerx, hitbox.bottom - 1.0),
        ttl=DASH_SHOCKWAVE_TTL,
    )
    fx_group.add(shockwave)
    return shockwave


def spawn_dash_trail(fx_group: pygame.sprite.Group, entity: Any) -> DashTrailParticle | None:
    """A curved trail particle behind the dasher.

    Curve, length and width are jittered per spawn: the trail used to be one
    shape stamped ten times a dash, and a regular pattern of identical marks
    is what a trail reads as when it is not jittered.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    if not _has_room(fx_group, "dash_trail"):
        return None
    direction = dash_direction(entity)
    rng = _puff_rng(entity)
    trail = DashTrailParticle(
        (
            hitbox.centerx - direction * rng.uniform(0.0, hitbox.width / 2.0),
            hitbox.centery + rng.uniform(-hitbox.height / 4.0, hitbox.height / 4.0),
        ),
        direction,
        ttl=DASH_TRAIL_TTL,
        curve=rng.uniform(-9.0, 9.0),
        length=DASH_TRAIL_LENGTH * rng.uniform(0.8, 1.25),
        width=DASH_TRAIL_WIDTH * rng.uniform(0.8, 1.15),
    )
    fx_group.add(trail)
    return trail


@dataclass(frozen=True)
class BurstSpec:
    """The look of an impact burst, as data."""

    colors: tuple[Color, ...]
    core: Color
    count: int
    speed: tuple[float, float]
    cone: float
    tilt: float = 0.0
    size: float = SPARK_SIZE
    elongation: float = 1.0
    ttl: float = SPARK_TTL
    ink: Color = FXColors.ink


BREAK_BURST = BurstSpec(
    colors=(FXColors.break_spark, Colors.orange),
    core=FXColors.break_core,
    count=BREAK_SPARK_COUNT,
    speed=(380.0, 300.0),
    cone=80.0,
    size=SPARK_SIZE * 1.5,
    elongation=1.6,
    ttl=SPARK_TTL + 0.12,
    ink=FXColors.ink_warm,
)


def _spawn_burst(
    fx_group: pygame.sprite.Group,
    entity: Any,
    spec: BurstSpec,
    origin: tuple[float, float] | None = None,
) -> list[SparkParticle]:
    """Throw ``spec.count`` sparks in a one-sided cone from the contact point."""
    if getattr(entity, "hitbox", None) is None or spec.count <= 0:
        return []
    if not _has_room(fx_group):
        return []
    rng = _puff_rng(entity)
    facing = 0.0 if facing_side(entity) >= 0.0 else math.pi
    start = _contact_point(entity, origin)
    sparks: list[SparkParticle] = []
    for index in range(spec.count):
        angle = facing + math.radians(spec.tilt + rng.uniform(-spec.cone, spec.cone))
        pace = rng.uniform(*spec.speed)
        spark = SparkParticle(
            start + Vector2((rng.uniform(-5.0, 5.0), rng.uniform(-8.0, 8.0))),
            (math.cos(angle) * pace, math.sin(angle) * pace),
            spec.colors[index % len(spec.colors)],
            ttl=spec.ttl,
            size=spec.size * rng.uniform(0.8, 1.2),
            core=spec.core,
            elongation=spec.elongation * rng.uniform(0.75, 1.35),
            ink=spec.ink,
        )
        fx_group.add(spark)
        sparks.append(spark)
    return sparks


def spawn_guard_arc(
    fx_group: pygame.sprite.Group, entity: Any, parried: bool = False
) -> ShieldArcParticle | None:
    """The block's arc, in front of the guard and facing the attacker.

    ``parried`` is the only difference a perfect block makes: same arc, same
    size, gold instead of cyan.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    if not _has_room(fx_group):
        return None
    side = facing_side(entity)
    arc = ShieldArcParticle(
        (hitbox.centerx + side * hitbox.width * 0.3, hitbox.centery),
        side,
        parried,
    )
    fx_group.add(arc)
    return arc


def spawn_break_burst(
    fx_group: pygame.sprite.Group,
    entity: Any,
    origin: tuple[float, float] | None = None,
) -> list[SparkParticle]:
    """The burst when a guard breaks: heavier shards, in the break colour."""
    return _spawn_burst(fx_group, entity, BREAK_BURST, origin)


def spawn_dizzy_stars(
    fx_group: pygame.sprite.Group,
    entity: Any,
    count: int = DIZZY_STAR_COUNT,
    ttl: float = DIZZY_STAR_TTL,
) -> list[OrbitParticle]:
    """Stars circling above a dizzy entity's head.

    Emitted on a cadence for as long as the entity is dizzy, like the swirl
    at its feet, and not from the parry that caused it. Spawning them on the
    block put a whole constellation on screen at the instant of the third
    parry, where it read as part of the block instead of as the state the
    block earned.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None or count <= 0:
        return []
    if not _has_room(fx_group, "dizzy_star"):
        return []
    rng = _puff_rng(entity)
    center = (hitbox.centerx, hitbox.top - 12.0)
    stars: list[OrbitParticle] = []
    for index in range(count):
        star = OrbitParticle(
            center,
            radius=DIZZY_STAR_RADIUS * rng.uniform(0.8, 1.15),
            phase=index * 2.0 * math.pi / count + rng.uniform(0.0, 0.6),
            speed=DIZZY_STAR_SPEED * rng.choice((-1.0, 1.0)),
            color=DIZZY_STAR_COLORS[index % len(DIZZY_STAR_COLORS)],
            core=FXColors.star_core,
            ttl=ttl,
            size=5.0 + rng.uniform(0.0, 1.5),
            bob=rng.uniform(0.0, 3.0),
        )
        fx_group.add(star)
        stars.append(star)
    return stars


def spawn_dizzy_vortex(fx_group: pygame.sprite.Group, entity: Any) -> DizzyVortexParticle | None:
    """A purple swirl at the feet of a dizzy entity.

    At the feet rather than over the head, because the head already has the
    circling stars on it and the two were drawn on top of each other.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    if not _has_room(fx_group, "dizzy_vortex"):
        return None
    vortex = DizzyVortexParticle(
        (hitbox.centerx, hitbox.bottom - 4.0),
        ttl=DIZZY_VORTEX_TTL,
    )
    fx_group.add(vortex)
    return vortex


def spawn_sweat_drops(fx_group: pygame.sprite.Group, entity: Any) -> list[SweatParticle]:
    """Pop ``Sweat.COUNT`` comic teardrops off the side of the head.

    Emitted while the entity sits out its dash penalty: each fat teardrop
    beads beside the crown, kicked sideways and briefly up before gravity
    drags it down.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None or Sweat.COUNT <= 0:
        return []
    if not _has_room(fx_group):
        return []
    rng = _puff_rng(entity)
    side = facing_side(entity)
    drops: list[SweatParticle] = []
    for _ in range(Sweat.COUNT):
        drop = SweatParticle(
            (
                hitbox.centerx
                + side * hitbox.width * rng.uniform(0.15, 0.5)
                + rng.uniform(-SWEAT_SPREAD, SWEAT_SPREAD) * hitbox.width,
                hitbox.top + rng.uniform(2.0, 7.0),
            ),
            (
                side * rng.uniform(30.0, 90.0),
                SWEAT_POP_UP * rng.uniform(0.5, 1.0),
            ),
            tint=rng.uniform(0.0, 0.25),
        )
        fx_group.add(drop)
        drops.append(drop)
    return drops


def iter_landing_entities(entities: Iterable[Any]) -> Iterable[tuple[Any, float]]:
    """Yield ``(entity, impact)`` for entities that just landed hard.

    ``Entity.update`` records the pre-move fall speed into ``landed_impact`` on
    the landing tick and zeroes it otherwise; this filters on
    ``Dust.MIN_FALL_SPEED`` so light hops stay clean.
    """
    for entity in entities:
        impact = float(getattr(entity, "landed_impact", 0.0) or 0.0)
        if impact >= Dust.MIN_FALL_SPEED:
            yield entity, impact
