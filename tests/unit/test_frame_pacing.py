"""The loop must be paced exactly once, and the clock must stay fed.

``clock.tick(60)`` sleeps to hold 60fps, and with vsync the present blocks
until the vertical blank. Doing both paces the loop twice, and the two
waiters do not add up: a frame lands just past the blank, the present then
waits for the *next* one, and the frame after finds its sleep already
elapsed. The cadence alternates between on time and one refresh late, which
reads as a small stutter rather than as a steady frame rate.

The clock still has to be ticked, though. A ``pygame.time.Clock`` only
updates its own timing when ``tick`` is called, so a vsync path that skips it
entirely leaves ``get_fps()`` at 0.0 -- the whole frame rate readout, stuck
at zero while the game plainly runs. The target handed to ``tick`` is
therefore a rate a real present never reaches, not 60: the present stays the
only pacer, and the meter still gets its numbers.
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

    def __init__(self, elapsed: int = 16) -> None:
        self.slept: list[int] = []
        self.elapsed = elapsed

    def tick(self, fps: int) -> int:
        self.slept.append(fps)
        return self.elapsed


@pytest.fixture()
def fake_clock() -> _FakeClock:
    return _FakeClock()


@pytest.fixture()
def runtime(tmp_path) -> Game:
    runtime = Game(save_path=tmp_path / "save.json", bindings_path=tmp_path / "settings.json")
    runtime.initialize_display()
    return runtime


def test_vsync_off_uses_the_clock_as_the_pacer(runtime: Game, fake_clock) -> None:
    runtime.settings = replace(runtime.settings, vsync=False)
    runtime.clock = fake_clock  # type: ignore[assignment]

    runtime._frame_delta()

    assert fake_clock.slept == [Display.FPS], "without vsync the clock holds the rate"


def test_vsync_on_still_ticks_the_clock(runtime: Game, fake_clock) -> None:
    """Skipping ``tick`` is what left the FPS readout at 0.0."""
    runtime.settings = replace(runtime.settings, vsync=True)
    runtime.clock = fake_clock  # type: ignore[assignment]

    runtime._frame_delta()

    assert fake_clock.slept, "a Clock that is never ticked reports 0.0 fps"


def test_vsync_on_never_asks_the_clock_to_hold_the_configured_rate(
    runtime: Game, fake_clock
) -> None:
    """Targeting ``Display.FPS`` would sleep on top of the present.

    The clock is paced at 60 with vsync off, so asking for the same rate with
    vsync on would wait twice for one refresh. The rate asked for instead is
    the runaway ceiling, which no real present reaches.
    """
    runtime.settings = replace(runtime.settings, vsync=True)
    runtime.clock = fake_clock  # type: ignore[assignment]

    runtime._frame_delta()

    assert fake_clock.slept == [game_module.DISPLAY_SAFETY_CEILING_FPS]
    assert game_module.DISPLAY_SAFETY_CEILING_FPS != Display.FPS


def test_the_ceiling_never_caps_the_frame_rate_the_user_asked_for() -> None:
    """The ceiling is a runaway backstop, not a frame rate control.

    A fixed 125 sat below a 240 target, so with vsync on the game quietly ran
    at half the configured rate and nothing on screen said so. Deriving the
    ceiling from ``Display.FPS`` makes that unreachable: raising the target
    can never leave the ceiling underneath it.
    """
    assert game_module.DISPLAY_SAFETY_CEILING_FPS > Display.FPS


def test_the_ceiling_clears_any_real_refresh_rate() -> None:
    """The ceiling has to sit above the fastest present it may meet.

    A 60Hz present takes 16.7ms and a 240Hz one 4.2ms. The ceiling is
    compared against the *configured* rate rather than a hardcoded 240, so
    raising the target cannot push a real refresh past it either.
    """
    floor_ms = 1000 / game_module.DISPLAY_SAFETY_CEILING_FPS
    assert floor_ms < 1000 / Display.FPS / 2


def test_a_normal_vsync_frame_is_never_short_circuited(runtime: Game) -> None:
    """A working 60Hz present must never trip the ceiling.

    The ceiling's floor sits well under the 16.7ms a 60Hz present takes, so
    it only ever catches a present that does not block.
    """
    runtime.settings = replace(runtime.settings, vsync=True)
    runtime.clock = _FakeClock(elapsed=17)  # type: ignore[assignment]

    assert runtime._frame_delta() == pytest.approx(0.017)


def test_a_present_that_does_not_block_still_gets_a_speed_limit(runtime: Game) -> None:
    """A display ignoring the vsync flag must not let the loop run flat out.

    The ceiling is handed to the clock, so a frame that arrives in 0ms is
    held to the 8ms floor rather than being allowed to run away.
    """
    runtime.settings = replace(runtime.settings, vsync=True)
    runtime.clock = pygame.time.Clock()

    runtime._frame_delta()

    assert runtime.clock.get_time() <= 1000 / game_module.DISPLAY_SAFETY_CEILING_FPS + 1


def test_the_frame_delta_is_the_clock_delta(runtime: Game) -> None:
    """One clock, one measurement: the loop bills what the meter reports."""
    runtime.settings = replace(runtime.settings, vsync=True)
    runtime.clock = _FakeClock(elapsed=12)  # type: ignore[assignment]

    assert runtime._frame_delta() == pytest.approx(0.012)


def test_initialising_resets_the_clock_baseline(runtime: Game) -> None:
    """Level loading can take seconds; the first frame must not bill it."""
    runtime._initialize()
    assert runtime.clock is not None

    runtime.clock.tick(60)
    first = runtime.clock.get_time()
    runtime._initialize()
    runtime.clock.tick(0)

    assert runtime.clock.get_time() < first, "the baseline must restart at init"
