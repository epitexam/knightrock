"""Cached frame ladders shared by the FX particles.

The shard ladder used to live inside :mod:`src.presentation.fx.particles` even though
it depends on no particle class: a paint cache keyed on a finite layout grid.
Keeping it here lets a ladder grow without reopening the sprites that consume
it. ``particles`` re-exports the two public names for existing callers.
"""

from __future__ import annotations

import random

import pygame

from src.presentation.fx.draw import draw_arc_stroke, snap
from src.presentation.fx.tuning import FxGuard
from src.shared.colors import Color, FXColors

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
