"""The loop must be paced exactly once.

``clock.tick(60)`` sleeps to hold 60fps, and with vsync the present blocks
until the vertical blank. Doing both paces the loop twice, and the two
waiters do not add up: a frame lands just past the blank, the present then
waits for the *next* one, and the frame after finds its sleep already
elapsed. The cadence alternates between on time and one refresh late, which
reads as a small stutter rather than as a steady frame rate.
"""

import os
from dataclasses import replace

import pygame
import pytest

from src.core import game as game_module
from src.core.game import Game
from src.core.settings import Display

pytestmark = pytest.mark.usefixtures("_pacing_display")


@pytest.fixture(scope="module", autouse=True)
def _pacing_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))


class _FakeClock:
    """A clock that records the rates it was asked to hold."""

    def __init__(self) -> None:
        self.slept: list[int] = []

    def tick(self, fps: int) -> int:
        self.slept.append(fps)
        return 16


@pytest.fixture()
def fake_clock() -> _FakeClock:
    return _FakeClock()


@pytest.fixture()
def runtime(tmp_path) -> Game:
    runtime = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    runtime.display_surface = pygame.display.get_surface()
    runtime._last_tick_ms = 1000
    return runtime


def test_vsync_off_uses_the_clock_as_the_pacer(runtime: Game, fake_clock) -> None:
    runtime.settings = replace(runtime.settings, vsync=False)
    runtime.clock = fake_clock  # type: ignore[assignment]

    runtime._frame_delta()

    assert fake_clock.slept == [Display.FPS], "without vsync the clock holds the rate"


def test_vsync_on_lets_the_present_pace(runtime: Game, fake_clock, monkeypatch) -> None:
    """Sleeping as well would wait twice for the same refresh."""
    runtime.settings = replace(runtime.settings, vsync=True)
    runtime.clock = fake_clock  # type: ignore[assignment]
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 1030)

    runtime._frame_delta()

    assert fake_clock.slept == [], "the present paces, the clock must not sleep"
    assert runtime._last_tick_ms == 1030


def test_vsync_on_bills_the_real_elapsed_time(runtime: Game, monkeypatch) -> None:
    runtime.settings = replace(runtime.settings, vsync=True)
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 1017)

    assert runtime._frame_delta() == pytest.approx(0.017)


def test_a_present_that_does_not_block_still_gets_a_speed_limit(runtime: Game, monkeypatch) -> None:
    """A display ignoring the vsync flag must not let the loop run flat out.

    A tight loop measures 0ms between frames, so the floor has to cover zero
    as well: guarding on ``0 < elapsed`` let exactly the runaway case through.
    """
    runtime.settings = replace(runtime.settings, vsync=True)
    waited: list[int] = []
    monkeypatch.setattr(pygame.time, "wait", waited.append)
    floor = game_module.DISPLAY_SAFETY_FLOOR_MS
    # First read is the frame length (0ms), second the moment after waiting.
    monkeypatch.setattr(pygame.time, "get_ticks", iter([1000, 1000 + floor]).__next__)

    runtime._frame_delta()

    assert waited == [floor]


def test_a_normal_vsync_frame_is_never_short_circuited(runtime: Game, monkeypatch) -> None:
    """The safety floor is below a real refresh, so a 60Hz present skips it."""
    runtime.settings = replace(runtime.settings, vsync=True)
    waited: list[int] = []
    monkeypatch.setattr(pygame.time, "wait", waited.append)
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 1017)

    runtime._frame_delta()

    assert waited == []


def test_initialising_resets_the_wall_clock(runtime: Game) -> None:
    """Level loading can take seconds; the first frame must not bill it."""
    runtime._last_tick_ms = 0

    runtime._initialize()

    assert runtime._last_tick_ms > 0
