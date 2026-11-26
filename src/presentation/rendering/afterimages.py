"""Afterimage plate colours and opacities, kept out of the renderer.

The owning state machine and the blit loop stay in
:mod:`src.presentation.rendering.renderer`; only the pure ladder arithmetic lives here.
"""

from __future__ import annotations

import pygame

from src.shared.colors import Color, FXColors
from src.simulation.settings import Afterimage


def _monochrome(image: pygame.Surface, tint: Color) -> pygame.Surface:
    """``image`` with its hue knocked back to one, keeping its shading.

    A manga speed line is a monochrome copy of the character: still the
    character, still lit from the same side, in one tone. So this keeps the
    luminance and drops the chroma, rather than filling the shape flat -- a
    flat fill also throws away the outline and the shading, and a row of
    those is a row of blobs.

    ``tint`` is multiplied over the result, so a near-white one cools the
    greyscale without darkening it much, and the ghost sits in the same
    family as the cyan the dashing sprite is lit with.
    """
    ghost = pygame.transform.grayscale(image.copy())
    ghost.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
    return ghost


def _ghost_tint(index: int) -> Color:
    """The tint of the ``index``-th ghost of a dash: pale first, then the dash's cyan.

    The trail reads in the direction of travel: the oldest stamp, furthest
    behind, is the palest, and each one nearer the fighter is more saturated.
    """
    t = min(1.0, index / max(1, Afterimage.TINT_STEPS))
    pale, deep = FXColors.speed_ghost, Afterimage.DEEP_TINT
    return (
        round(pale[0] + (deep[0] - pale[0]) * t),
        round(pale[1] + (deep[1] - pale[1]) * t),
        round(pale[2] + (deep[2] - pale[2]) * t),
    )


def _ghost_alpha(ttl: float) -> int:
    """The opacity a ghost of this remaining life is stamped at.

    A ladder, not a slope: each level holds for an equal share of the ghost's
    life, so a dashing player leaves a few flat plates rather than a blur.
    """
    levels = Afterimage.LEVELS
    share = Afterimage.TTL / len(levels)
    remaining = min(len(levels) - 1, int(max(0.0, ttl) / share))
    return levels[len(levels) - 1 - remaining]
