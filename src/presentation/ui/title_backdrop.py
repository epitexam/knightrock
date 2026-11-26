"""The title screen's backdrop: a dark field with embers drifting up.

Slow and dim on purpose -- it is behind a menu, and a background that pulls the
eye competes with the rows. Everything is placed on a grid of ``unit`` pixels,
the menu font's own pixel, so the embers are squares of the same grain as the
letters.

Deterministic: the embers come from a fixed seed and move with the time the
screen has been up, so a frame at a given time is always the same picture.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

#: The backdrop's top and bottom colours; the field darkens towards the top.
TOP = (14, 16, 22)
BOTTOM = (30, 26, 32)
#: The ember colours, from the dimmest to the brightest.
EMBERS = ((92, 58, 34), (150, 92, 40), (214, 150, 60))
EMBER_COUNT = 48
#: How many gradient bands the field is painted in: banded, like the art.
BANDS = 12


@dataclass(frozen=True)
class _Ember:
    x: float  # 0..1 across
    phase: float  # 0..1 up the screen at time zero
    speed: float  # screens per second
    sway: float  # 0..1 of a column, side to side
    size: int  # in units
    shade: int  # index into EMBERS


class TitleBackdrop:
    def __init__(self, seed: int = 7) -> None:
        rng = random.Random(seed)
        self._embers = tuple(
            _Ember(
                x=rng.random(),
                phase=rng.random(),
                speed=rng.uniform(0.015, 0.045),
                sway=rng.uniform(0.004, 0.012),
                size=rng.choice((1, 1, 1, 2)),
                shade=rng.choice((0, 0, 1, 1, 2)),
            )
            for _ in range(EMBER_COUNT)
        )
        self._field: pygame.Surface | None = None
        self.time = 0.0

    def update(self, delta_time: float) -> None:
        self.time += delta_time

    def draw(self, surface: pygame.Surface, unit: int) -> None:
        width, height = surface.get_size()
        surface.blit(self._field_for(surface.get_size()), (0, 0))
        u = max(1, unit)
        for ember in self._embers:
            rise = (ember.phase + ember.speed * self.time) % 1.0
            y = height - rise * (height + u * 4)
            x = (ember.x + ember.sway * math.sin(self.time * 0.6 + ember.phase * 6.28)) * width
            # Embers fade out as they rise into the dark.
            shade = ember.shade if rise < 0.7 else max(0, ember.shade - 1)
            side = ember.size * u
            surface.fill(
                EMBERS[shade],
                pygame.Rect(int(x) // u * u, int(y) // u * u, side, side),
            )

    def _field_for(self, size: tuple[int, int]) -> pygame.Surface:
        """The banded gradient, painted once per size."""
        if self._field is None or self._field.get_size() != size:
            field = pygame.Surface(size)
            width, height = size
            for band in range(BANDS):
                t = band / (BANDS - 1)
                color = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM, strict=True))
                top = height * band // BANDS
                bottom = height * (band + 1) // BANDS
                field.fill(color, pygame.Rect(0, top, width, bottom - top))
            self._field = field
        return self._field
