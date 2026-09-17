"""Render-only impact FX: landing dust puffs and dash streaks.

Dust lives in ``groups.fx_sprites`` (no collision, no damage): it is
integrated by :class:`PhysicsSystem`, drawn by :class:`Renderer` like any
visible sprite, and deliberately excluded from rollback snapshots and
golden digests — pure juice, zero simulation impact.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from typing import Any

import pygame
from pygame.math import Vector2

from src.core.colors import Colors
from src.core.settings import Dust, Sweat

__all__ = [
    "DustParticle",
    "StreakParticle",
    "SweatParticle",
    "dash_direction",
    "iter_landing_entities",
    "particle_frames",
    "spawn_dash_burst",
    "spawn_dash_dust",
    "spawn_dash_streak",
    "spawn_landing_dust",
    "spawn_sweat_drops",
]

#: Puff base size (px) before the per-particle jitter.
DUST_RADIUS = 5.0
#: Upward drift so puffs hang briefly instead of dropping like stones.
DUST_RISE = -60.0
#: Horizontal drag applied to puff velocity (per second).
DUST_DRAG = 4.0
#: Puffs kicked out when a dash starts (rising edge, once per dash).
DASH_BURST_COUNT = 5
#: Safety cap: the spawner skips new puffs once the fx group is this full.
MAX_FX_SPRITES = 64
#: Shipped debris frames, cycled as a shrink-out puff when present.
PARTICLE_FRAMES_DIR = "assets/graphics/effects/particle"
#: Frame upscale so the tiny shipped specks read at gameplay distance.
PARTICLE_FRAME_SCALE = 2.0
#: Speed-streak look: near-white cyan lines, short and fast.
STREAK_COLOR = (200, 240, 255)
STREAK_TTL = 0.22
#: Sweat look: comic-book teardrops beading off an exhausted dasher.
SWEAT_COLOR = (150, 240, 245)
#: Bold ink outline around the bead, comic-panel style.
SWEAT_OUTLINE = (20, 60, 90)
SWEAT_OUTLINE_WIDTH = 2
#: Glossy glint on the bead, so it reads as liquid and not a ball.
SWEAT_SHINE = (240, 255, 255)
#: Fat comic beads: they must read at gameplay distance.
SWEAT_RADIUS = 5.0
#: Headroom so the teardrop tip and its outline stay inside the surface.
SWEAT_MARGIN = 2
#: Initial upward pop before gravity takes the droplet down.
SWEAT_POP_UP = -110.0
#: Droplets are heavier than dust: they arc down instead of hanging.
SWEAT_GRAVITY = 620.0
#: Lateral jitter as a fraction of the hitbox width: hug the crown.
SWEAT_SPREAD = 0.12


class DustParticle(pygame.sprite.Sprite):
    """A single fading dust puff: linear drift, alpha fade, then ``kill``.

    With ``frames`` (the shipped debris strip) the puff shrink-cycles
    through them over its life; without (bare checkout, headless tests) it
    falls back to a plain fading circle. Cached library frames are never
    mutated — scaled copies are made per puff.
    """

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = Dust.TTL,
        radius: float = DUST_RADIUS,
        frames: list[pygame.Surface] | None = None,
    ) -> None:
        super().__init__()
        self.pos = Vector2(pos)
        self.velocity = Vector2(velocity)
        self.ttl = float(ttl)
        self.max_ttl = float(ttl) if ttl > 0.0 else 1.0
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
        self.radius = float(radius)
        self.image = self._render(0)
        self.rect: pygame.FRect = self.image.get_frect(center=self.pos)

    def _render(self, frame_index: int) -> pygame.Surface:
        """The puff look at ``frame_index`` (framed strip or plain circle)."""
        if self.frames:
            return self.frames[min(frame_index, len(self.frames) - 1)].copy()
        side = max(2, int(self.radius * 2.0))
        surface = pygame.Surface((side, side), pygame.SRCALPHA)
        pygame.draw.circle(surface, Colors.light_grey, (side // 2, side // 2), side // 2)
        return surface

    def update(self, delta_time: float) -> None:
        """Drift, fade (and shrink-cycle framed puffs), reap when done."""
        self.ttl -= delta_time
        if self.ttl <= 0.0:
            self.kill()
            return
        drag = max(0.0, 1.0 - DUST_DRAG * delta_time)
        self.velocity.x *= drag
        self.velocity.y += DUST_RISE * delta_time
        self.pos += self.velocity * delta_time
        self.rect.center = self.pos
        if self.frames:
            elapsed = 1.0 - self.ttl / self.max_ttl
            self.image = self._render(int(elapsed * len(self.frames)))
            self.rect = self.image.get_frect(center=self.pos)
        assert self.image is not None
        self.image.set_alpha(int(255 * self.ttl / self.max_ttl))


class StreakParticle(pygame.sprite.Sprite):
    """A thin speed line: kicked backward, fades fast, then ``kill``."""

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        length: float = 24.0,
        ttl: float = STREAK_TTL,
    ) -> None:
        super().__init__()
        self.pos = Vector2(pos)
        self.velocity = Vector2(velocity)
        self.ttl = float(ttl)
        self.max_ttl = float(ttl) if ttl > 0.0 else 1.0
        self.image = pygame.Surface((max(1, int(length)), 3), pygame.SRCALPHA)
        self.image.fill(STREAK_COLOR)
        self.rect: pygame.FRect = self.image.get_frect(center=self.pos)

    def update(self, delta_time: float) -> None:
        """Slide backward, fade out, and reap the streak once done."""
        self.ttl -= delta_time
        if self.ttl <= 0.0:
            self.kill()
            return
        self.pos += self.velocity * delta_time
        self.rect.center = self.pos
        assert self.image is not None
        self.image.set_alpha(int(255 * self.ttl / self.max_ttl))


class SweatParticle(pygame.sprite.Sprite):
    """A single sweat droplet: pops off the head, arcs down, fades, dies.

    Heavier than dust — the pop impulse is immediately fought by gravity
    so the droplet traces a short nervous fountain before winking out.
    """

    def __init__(
        self,
        pos: tuple[float, float] | Vector2,
        velocity: tuple[float, float] | Vector2,
        ttl: float = Sweat.TTL,
        radius: float = SWEAT_RADIUS,
    ) -> None:
        super().__init__()
        self.pos = Vector2(pos)
        self.velocity = Vector2(velocity)
        self.ttl = float(ttl)
        self.max_ttl = float(ttl) if ttl > 0.0 else 1.0
        self.radius = float(radius)
        self.image = self._render()
        self.rect: pygame.FRect = self.image.get_frect(center=self.pos)

    def _render(self) -> pygame.Surface:
        """The comic-book droplet: fat teardrop, bold ink outline, glint."""
        radius = int(self.radius)
        outline = SWEAT_OUTLINE_WIDTH
        tip = radius  # tapered top rises one radius above the bulb
        margin = SWEAT_MARGIN
        width = 2 * (radius + outline + margin)
        height = tip + 2 * radius + 2 * outline + 2 * margin
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        cx = width // 2
        bulb_cy = height - margin - outline - radius
        # Ink silhouette: round bulb plus a pointed top, oversized so the
        # fill leaves an ink rim all around (classic comic inking).
        pygame.draw.circle(surface, SWEAT_OUTLINE, (cx, bulb_cy), radius + outline)
        pygame.draw.polygon(
            surface,
            SWEAT_OUTLINE,
            [
                (cx, margin - outline),
                (cx + radius + outline, bulb_cy - radius // 2),
                (cx - radius - outline, bulb_cy - radius // 2),
            ],
        )
        # Fill, inset by the outline width.
        pygame.draw.circle(surface, SWEAT_COLOR, (cx, bulb_cy), radius)
        pygame.draw.polygon(
            surface,
            SWEAT_COLOR,
            [
                (cx, margin),
                (cx + radius - outline // 2, bulb_cy - radius // 2),
                (cx - radius + outline // 2, bulb_cy - radius // 2),
            ],
        )
        # Glossy glint, upper-left of the bulb: liquid shine, not a ball.
        pygame.draw.circle(
            surface,
            SWEAT_SHINE,
            (cx - radius // 2, bulb_cy - radius // 3),
            max(1, radius // 3),
        )
        return surface

    def update(self, delta_time: float) -> None:
        """Fall under gravity, fade out, and reap the droplet once done."""
        self.ttl -= delta_time
        if self.ttl <= 0.0:
            self.kill()
            return
        self.velocity.y += SWEAT_GRAVITY * delta_time
        self.pos += self.velocity * delta_time
        self.rect.center = self.pos
        assert self.image is not None
        self.image.set_alpha(int(255 * self.ttl / self.max_ttl))


_frames_cache: list[pygame.Surface] | None = None
_frames_miss = False


def particle_frames() -> list[pygame.Surface] | None:
    """The shipped debris strip, or None on a bare checkout (fallback art).

    Memoized: the library caches converted frames, and the miss (no
    ``assets/`` tree, e.g. some CI checkouts) is remembered too.
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


def _puff_rng(entity: Any) -> random.Random:
    """The entity's own RNG when it has one, else a throwaway instance."""
    rng = getattr(entity, "rng", None)
    if isinstance(rng, random.Random):
        return rng
    return random.Random()


def dash_direction(entity: Any) -> float:
    """Signed dash direction: live velocity wins, facing is the fallback.

    Velocity is authoritative mid-dash (air dashes, turnarounds); facing
    only matters on the very first tick before the dash speed kicks in.
    """
    velocity = getattr(entity, "velocity", None)
    vx = float(getattr(velocity, "x", 0.0) or 0.0)
    if abs(vx) > 1.0:
        return 1.0 if vx > 0.0 else -1.0
    return 1.0 if bool(getattr(entity, "facing_right", True)) else -1.0


def spawn_landing_dust(fx_group: pygame.sprite.Group, entity: Any) -> list[DustParticle]:
    """Fan ``Dust.COUNT`` puffs out of the entity's feet. Returns the puffs."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return []
    rng = _puff_rng(entity)
    frames = particle_frames()
    puffs: list[DustParticle] = []
    for index in range(Dust.COUNT):
        # Symmetric fan: outer puffs fly wider, every other puff hops higher.
        side = index - (Dust.COUNT - 1) / 2.0
        velocity = (
            side * 55.0 + rng.uniform(-20.0, 20.0),
            -abs(rng.uniform(60.0, 160.0)) - (40.0 if index % 2 == 0 else 0.0),
        )
        puff = DustParticle(
            (hitbox.centerx + side * 4.0, hitbox.bottom - 2.0),
            velocity,
            radius=DUST_RADIUS + rng.uniform(0.0, 3.0),
            frames=frames,
        )
        fx_group.add(puff)
        puffs.append(puff)
    return puffs


def spawn_dash_dust(fx_group: pygame.sprite.Group, entity: Any) -> DustParticle | None:
    """A single streak puff kicked backward off the dasher's feet."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    direction = dash_direction(entity)
    rng = _puff_rng(entity)
    puff = DustParticle(
        (
            hitbox.centerx - direction * hitbox.width / 2.0,
            hitbox.bottom - 4.0,
        ),
        (
            -direction * rng.uniform(90.0, 160.0),
            rng.uniform(-60.0, -10.0),
        ),
        ttl=Dust.TTL * 0.75,
        radius=DUST_RADIUS * 0.8,
    )
    fx_group.add(puff)
    return puff


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
    fx_group.add(streak)
    return streak


def spawn_sweat_drops(fx_group: pygame.sprite.Group, entity: Any) -> list[SweatParticle]:
    """Pop ``Sweat.COUNT`` comic teardrops off the entity's head.

    Emitted while the entity sits out its dash penalty (every charge
    spent): each fat teardrop beades just above the crown with a slight
    jittered sideways kick and pops briefly up before gravity drags it
    down.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None or Sweat.COUNT <= 0:
        return []
    rng = _puff_rng(entity)
    drops: list[SweatParticle] = []
    for _ in range(Sweat.COUNT):
        drop = SweatParticle(
            (
                hitbox.centerx + rng.uniform(-SWEAT_SPREAD, SWEAT_SPREAD) * hitbox.width,
                hitbox.top + 1.0,
            ),
            (
                rng.uniform(-70.0, 70.0),
                SWEAT_POP_UP * rng.uniform(0.5, 1.0),
            ),
        )
        fx_group.add(drop)
        drops.append(drop)
    return drops


def iter_landing_entities(entities: Iterable[Any]) -> Iterable[tuple[Any, float]]:
    """Yield ``(entity, impact)`` for entities that just landed hard.

    ``Entity.update`` records the pre-move fall speed into
    ``landed_impact`` on the landing tick and zeroes it otherwise; this
    helper filters on ``Dust.MIN_FALL_SPEED`` so light hops stay clean.
    """
    for entity in entities:
        impact = float(getattr(entity, "landed_impact", 0.0) or 0.0)
        if impact >= Dust.MIN_FALL_SPEED:
            yield entity, impact
