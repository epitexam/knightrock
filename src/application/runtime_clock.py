"""The frame pacer, behind a small port so tests can drive frames without sleeping."""

from __future__ import annotations

from typing import Protocol

import pygame


class FrameClock(Protocol):
    """What the loop needs from a clock: pacing, plus the debug overlay's stats."""

    def tick(self, framerate: int) -> float:
        """Advance one frame and return seconds elapsed since the previous one."""
        ...

    def get_fps(self) -> float:
        """The clock's own FPS reading, for the debug overlay."""
        ...

    def get_time(self) -> int:
        """The last frame's duration in milliseconds, for the debug overlay."""
        ...


class PygameFrameClock:
    """The production clock: ``pygame.time.Clock`` with seconds as the unit."""

    def __init__(self) -> None:
        self._clock = pygame.time.Clock()

    def tick(self, framerate: int) -> float:
        return self._clock.tick(framerate) / 1000.0

    def get_fps(self) -> float:
        return self._clock.get_fps()

    def get_time(self) -> int:
        return self._clock.get_time()


class ManualFrameClock:
    """A clock advanced by the test, not by wall time.

    A frame driven through ``Game.step()`` with this clock returns exactly
    ``delta`` seconds, so a suite can simulate a hitch or a 240 Hz display
    without monkeypatching pygame or sleeping.
    """

    def __init__(self, delta: float = 1 / 60) -> None:
        self.delta = delta
        self.ticks = 0

    def tick(self, framerate: int) -> float:
        del framerate
        self.ticks += 1
        return self.delta

    def get_fps(self) -> float:
        return 0.0

    def get_time(self) -> int:
        return int(self.delta * 1000)
