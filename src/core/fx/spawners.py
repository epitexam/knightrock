"""Deciding whether a particle is allowed, and putting it in the plane.

Every spawner here does the same three things in the same order: read the
entity it is decorating, ask the budget whether this family can still spend,
and add exactly one particle. The order is the point. A spawner that adds
first and checks afterwards has already spent what it was not allowed to.

The budgets and the plane-wide cap are declared here rather than in
``particles`` because they are the module's contract with the plane: the
invariant tests read them from this file, and a particle has no business
knowing how many of its siblings are allowed to exist.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable
from typing import Any

import pygame
from pygame.math import Vector2

from src.core.colors import Color, Colors, FXColors
from src.core.fx.particles import (
    DashBurstPuff,
    DashShockwaveParticle,
    DashTrailParticle,
    DizzyVortexParticle,
    DustParticle,
    ImpactDecalParticle,
    OrbitParticle,
    ShatterArcParticle,
    ShieldArcParticle,
    StreakParticle,
    SweatParticle,
    WindLine,
    particle_frames,
)
from src.core.settings import Dust, FxDash, FxDecal, FxDizzy, Sweat

DIZZY_STAR_COLORS: tuple[Color, ...] = (FXColors.star, FXColors.star_core, Colors.gold)
"""The palette a star is drawn from, cycling. A colour list rather than one
colour so a ring of six does not read as six identical marks."""

MAX_FX_SPRITES = 64
"""The whole plane's ceiling. The per-family table below is what keeps any
one effect from spending it all."""

FX_FAMILY_BUDGETS: dict[str, int] = {
    "dash_trail": 26,
    "landing_dust": 16,
    "dash_burst": 16,
    "dash_streak": 24,
    "dash_wind": 12,
    "dash_shockwave": 4,
    "dizzy_star": 8,
    "dizzy_vortex": 8,
    "impact_decal": 8,
    "shield_arc": 4,
    "shatter_arc": 4,
    "sweat": 6,
}
"""Per-family caps, on top of :data:`MAX_FX_SPRITES`.

The global cap alone lets one effect starve the others: a parry, a burst and
a land on the same tick can fill the plane, and the dash trail -- which has
to keep animating for as long as the dash does -- silently stops. Sizing the
cadenced effects generously and the one-shot events tightly keeps the plane a
collection of events instead of one effect filling it.

Every family a particle declares is in here; ``test_fx_invariants`` reads the
source to keep it that way, because the key is a string and a typo would
otherwise mean a particle spending from a budget that does not exist.
"""


_fx_rng: random.Random = random.Random()
"""The FX module's own stream, deliberately outside the snapshot.

This used to be ``entity.rng``, which the rollback snapshot captures and
restores. A render-only effect drawing from it advanced state the simulation
owns, so the position in the stream became a function of how much juice
happened to be on screen -- harmless while nothing read the stream, and a
determinism bug the moment something did.

A private stream costs the one thing the shared RNG was buying: the visuals
are no longer reproducible across a rollback rewind. That is the right
trade, because the particles themselves are not restored by a rewind either,
so the FX plane was already inconsistent afterwards, and no golden hashes it.
"""


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


def _has_room(fx_group: pygame.sprite.Group, family: str | None = None, count: int = 1) -> bool:
    """Whether ``count`` particles fit, under the global cap and the family one.

    ``count`` rather than one, because a spawner that adds a fan asks once.
    Checking room for one and then adding six made the table a threshold
    rather than a cap: `dizzy_star` is budgeted at 8 and reached 12, and
    `landing_dust` at 16 and reached 18. A number in a table called a budget
    has to be the number that holds.
    """
    if len(fx_group) + count > MAX_FX_SPRITES:
        return False
    if family is None:
        return True
    cap = FX_FAMILY_BUDGETS.get(family)
    if cap is None:
        return True
    spent = sum(1 for sprite in fx_group if getattr(sprite, "family", "") == family)
    return spent + count <= cap


def _landing_strength(impact: float) -> float:
    """How big a landing reads, from the fall speed that caused it."""
    low, high = Dust.STRENGTH_RANGE
    return min(high, max(low, float(impact) / (Dust.MIN_FALL_SPEED * Dust.STRENGTH_PER_FALL)))


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
    if hitbox is None or not _has_room(fx_group, "landing_dust", Dust.COUNT):
        return []
    rng = _fx_rng
    frames = particle_frames()
    strength = _landing_strength(impact)
    puffs: list[DustParticle] = []
    for index in range(Dust.COUNT):
        side = index - (Dust.COUNT - 1) / 2.0
        velocity = (
            side * Dust.SPREAD * strength + rng.uniform(-Dust.SPREAD_JITTER, Dust.SPREAD_JITTER),
            -abs(rng.uniform(*Dust.RISE_RANGE)) * strength
            - (Dust.RISE_ALTERNATE if index % 2 == 0 else 0.0),
        )
        puff = DustParticle(
            (hitbox.centerx + side * 4.0, hitbox.bottom - 2.0),
            velocity,
            radius=Dust.PUFF_RADIUS * strength + rng.uniform(0.0, Dust.RADIUS_JITTER),
            frames=frames,
        )
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
        width=FxDecal.RADIUS * _landing_strength(impact),
    )
    fx_group.add(decal)
    return decal


def spawn_dash_burst(
    fx_group: pygame.sprite.Group,
    entity: Any,
    count: int = FxDash.BURST_COUNT,
) -> list[DustParticle]:
    """Kick a fan of dust backward as the dash starts (rising edge only)."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None or count <= 0 or not _has_room(fx_group, "dash_burst", count):
        return []
    direction = dash_direction(entity)
    rng = _fx_rng
    frames = particle_frames()
    puffs: list[DustParticle] = []
    for index in range(count):
        spread = index - (count - 1) / 2.0
        puff = DashBurstPuff(
            (
                hitbox.centerx - direction * hitbox.width / 2.0,
                hitbox.bottom - FxDash.BURST_LIFT + spread * FxDash.BURST_STEP,
            ),
            (
                -direction * rng.uniform(*FxDash.BURST_SPEED),
                -abs(rng.uniform(*FxDash.BURST_RISE)),
            ),
            radius=Dust.PUFF_RADIUS + rng.uniform(*FxDash.BURST_RADIUS_JITTER),
            frames=frames,
        )
        fx_group.add(puff)
        puffs.append(puff)
    return puffs


def spawn_dash_streak(fx_group: pygame.sprite.Group, entity: Any) -> StreakParticle | None:
    """A speed line trailing the dasher: thin, fast, gone in a blink."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None or not _has_room(fx_group, "dash_streak"):
        return None
    direction = dash_direction(entity)
    rng = _fx_rng
    streak = StreakParticle(
        (
            hitbox.centerx - direction * rng.uniform(0.0, hitbox.width / 2.0),
            hitbox.centery + rng.uniform(-hitbox.height / 3.0, hitbox.height / 3.0),
        ),
        (-direction * rng.uniform(*FxDash.STREAK_SPEED), 0.0),
        length=rng.uniform(*FxDash.STREAK_LENGTH_JITTER),
    )
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
    if not _has_room(fx_group, "dash_wind", FxDash.WIND_LINES):
        return []
    direction = dash_direction(entity)
    rng = _fx_rng
    pace = abs(float(getattr(getattr(entity, "velocity", None), "x", 0.0) or 0.0))
    lines: list[StreakParticle] = []
    for _ in range(FxDash.WIND_LINES):
        line = WindLine(
            (
                hitbox.centerx + direction * hitbox.width * rng.uniform(*FxDash.WIND_AHEAD),
                hitbox.centery + rng.uniform(-hitbox.height / 2.0, hitbox.height / 2.0),
            ),
            (-direction * (pace + rng.uniform(*FxDash.WIND_EXTRA_SPEED)), 0.0),
            length=rng.uniform(*FxDash.WIND_LENGTH_JITTER),
            thickness=FxDash.WIND_THICKNESS,
        )
        fx_group.add(line)
        lines.append(line)
    return lines


def spawn_dash_shockwave(
    fx_group: pygame.sprite.Group, entity: Any
) -> DashShockwaveParticle | None:
    """A ground ring at the entity's feet on dash start."""
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None or not _has_room(fx_group, "dash_shockwave"):
        return None
    shockwave = DashShockwaveParticle(
        (hitbox.centerx, hitbox.bottom - 1.0),
        ttl=FxDash.SHOCKWAVE_TTL,
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
    rng = _fx_rng
    trail = DashTrailParticle(
        (
            hitbox.centerx - direction * rng.uniform(0.0, hitbox.width / 2.0),
            hitbox.centery + rng.uniform(-hitbox.height / 4.0, hitbox.height / 4.0),
        ),
        direction,
        ttl=FxDash.TRAIL_TTL,
        curve=rng.uniform(-FxDash.TRAIL_CURVE, FxDash.TRAIL_CURVE),
        length=FxDash.TRAIL_LENGTH * rng.uniform(*FxDash.TRAIL_LENGTH_JITTER),
        width=FxDash.TRAIL_WIDTH * rng.uniform(*FxDash.TRAIL_WIDTH_JITTER),
    )
    fx_group.add(trail)
    return trail


def _guard_stance(entity: Any, contact: tuple[float, float] | None) -> tuple[Vector2, float] | None:
    """Where a guard's ring stands, and which way it opens.

    The contact point when the caller knows it, which is the only thing that
    says where the block actually landed. Without one, the ring goes in front
    of the defender, on the side they face.

    The side comes from the contact rather than from ``facing_right``, so a
    fighter blocking a hit that arrived from behind gets the ring on the side
    the hit came from. It used to open towards the guard's own facing, which
    put it on the wrong side of the body for every back-turned block.
    """
    hitbox = getattr(entity, "hitbox", None)
    if hitbox is None:
        return None
    if contact is None:
        side = facing_side(entity)
        return Vector2(hitbox.centerx + side * hitbox.width * 0.3, hitbox.centery), side
    at = Vector2(contact)
    offset = at.x - hitbox.centerx
    side = 1.0 if offset >= 0.0 else -1.0
    return at, side


def spawn_guard_arc(
    fx_group: pygame.sprite.Group,
    entity: Any,
    parried: bool = False,
    contact: tuple[float, float] | None = None,
) -> ShieldArcParticle | None:
    """The block's arc, at the contact and opening away from the defender.

    ``parried`` is the only difference a perfect block makes: same arc, same
    size, gold instead of cyan.
    """
    stance = _guard_stance(entity, contact)
    if stance is None or not _has_room(fx_group, "shield_arc"):
        return None
    arc = ShieldArcParticle(stance[0], stance[1], parried)
    fx_group.add(arc)
    return arc


def spawn_shatter_arc(
    fx_group: pygame.sprite.Group,
    entity: Any,
    contact: tuple[float, float] | None = None,
) -> ShatterArcParticle | None:
    """The ring breaking, on the side the guard gave way on.

    Stands where the block's ring stands and does the same job with the same
    silhouette: a guard that failed is the same shield, on the way out.
    """
    stance = _guard_stance(entity, contact)
    if stance is None or not _has_room(fx_group, "shatter_arc"):
        return None
    shatter = ShatterArcParticle(stance[0], stance[1], seed=_fx_rng.randrange(1 << 16))
    fx_group.add(shatter)
    return shatter


def spawn_dizzy_stars(
    fx_group: pygame.sprite.Group,
    entity: Any,
    count: int = FxDizzy.STAR_COUNT,
    ttl: float = FxDizzy.STAR_TTL,
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
    if not _has_room(fx_group, "dizzy_star", count):
        return []
    rng = _fx_rng
    base_size, size_jitter = FxDizzy.STAR_SIZE
    center = (hitbox.centerx, hitbox.top - FxDizzy.STAR_LIFT)
    stars: list[OrbitParticle] = []
    for index in range(count):
        star = OrbitParticle(
            center,
            radius=FxDizzy.STAR_RADIUS * rng.uniform(*FxDizzy.STAR_RADIUS_JITTER),
            phase=index * 2.0 * math.pi / count + rng.uniform(0.0, FxDizzy.STAR_PHASE_JITTER),
            speed=FxDizzy.STAR_SPEED * rng.choice((-1.0, 1.0)),
            color=DIZZY_STAR_COLORS[index % len(DIZZY_STAR_COLORS)],
            core=FXColors.star_core,
            ttl=ttl,
            size=base_size + rng.uniform(0.0, size_jitter),
            bob=rng.uniform(0.0, FxDizzy.STAR_BOB),
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
        ttl=FxDizzy.VORTEX_TTL,
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
    if not _has_room(fx_group, "sweat", Sweat.COUNT):
        return []
    rng = _fx_rng
    side = facing_side(entity)
    drops: list[SweatParticle] = []
    for _ in range(Sweat.COUNT):
        drop = SweatParticle(
            (
                hitbox.centerx
                + side * hitbox.width * rng.uniform(*Sweat.TEMPLE)
                + rng.uniform(-Sweat.SPREAD, Sweat.SPREAD) * hitbox.width,
                hitbox.top + rng.uniform(*Sweat.CROWN),
            ),
            (
                side * rng.uniform(*Sweat.KICK_X),
                Sweat.POP_UP * rng.uniform(*Sweat.POP_JITTER),
            ),
            tint=rng.uniform(*Sweat.TINT),
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
