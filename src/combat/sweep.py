"""Bounded swept-box geometry shared by attack and hurt rectangles (P1, D1/D4).

The sweep decision is purely geometric and identical on both sides of a
contact test:

- ``prev`` missing (spawn, first tick, capture not yet run) or a resize
  (different size between the two ticks) -> ``cur``, no smear possible;
- centre displacement below ``SWEEP_MIN_DISPLACEMENT_PX`` -> ``cur``
  (golden stability: a sub-threshold nudge must not widen the box);
- displacement above ``SWEEP_MAX_DISPLACEMENT_PX`` (teleport, respawn,
  abnormal carry) -> ``cur`` (no giant smear, no phantom hit);
- otherwise -> ``prev.union(cur)``: the classic CCD tunneling fix.

``dt`` is the fixed simulation timestep (``game.py`` fixed-step loop), so a
fixed ceiling is enough: no dt spike can inflate a per-tick displacement.
"""

from __future__ import annotations

import math

import pygame

from src.core.settings import Combat as CombatSettings

_MIN = CombatSettings.SWEEP_MIN_DISPLACEMENT_PX
_MAX = CombatSettings.SWEEP_MAX_DISPLACEMENT_PX


def swept_box(
    prev: pygame.FRect | None,
    cur: pygame.FRect,
    *,
    min_px: float = _MIN,
    max_px: float = _MAX,
) -> pygame.FRect:
    """Return the swept rectangle between ``prev`` and ``cur``.

    Parameters
    ----------
    prev :
        Rectangle captured at the previous tick boundary, or ``None``
        when no origin has been captured yet.
    cur :
        Live rectangle at the end of the current tick.
    min_px :
        Displacement threshold below which sweeping is skipped (D1).
    max_px :
        Displacement ceiling above which sweeping is skipped (D4).

    Returns
    -------
    pygame.FRect
        A fresh rectangle: ``cur`` when unswept, ``prev.union(cur)``
        otherwise. The inputs are never mutated nor aliased.
    """
    if prev is None or (prev.width, prev.height) != (cur.width, cur.height):
        return cur.copy()
    displacement = math.hypot(cur.centerx - prev.centerx, cur.centery - prev.centery)
    if displacement < min_px or displacement > max_px:
        return cur.copy()
    return prev.union(cur)
