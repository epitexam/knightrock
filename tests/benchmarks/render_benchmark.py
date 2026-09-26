"""Cost of one presented frame, broken into the parts that are now separate.

Run it from the repo root::

    uv run python tests/benchmarks/render_benchmark.py

It measures the two halves of a frame that this rework pulled apart: drawing
the world into the fixed render target, and scaling that target onto a window.
They used to be one thing -- the window *was* the target -- and the reason they
are worth measuring apart is that only the second one depends on the player's
video settings.

Two numbers decide a design choice, and neither could be measured before:

- **presentation cost is a function of the window, not the target.** Halving
  the render scale does not make the scaling cheaper; it only makes the
  sprites smaller. So the render scale is a sharpness setting, not a
  performance one, and the way to buy frames back is a smaller window or the
  nearest-neighbour path.
- **the world draw is a function of the target.** A 3x target is nine times the
  pixels of a 1x one, so the scale is not free either.

Measured here (2.19 / 4.22 / 7.77 ms for the draw at 1x / 2x / 3x, and
3.95 -> 13.32 ms for smooth scaling from 1280x720 to 3840x2160), the two add up
to 60% of a 60Hz frame at 1080p, 70% at 1440p, 82% at 3440x1440 and 105% at
4K. The default is smooth scaling with a 2x target, which does not fit a 4K
frame: that is what the Smoothing and Render scale rows in the video menu are
for, and turning either off brings 4K back inside the budget.

The dummy SDL driver has no fast renderer, so these are CPU-only figures. That
is representative for the scaling, which pygame does on the CPU for a software
surface whether or not a GPU is present; it understates a real window's
compositing. The ratios between rows are the actionable part.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.viewport import Viewport
from src.core.input.input_manager import InputManager
from src.core.level.level import Level
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.sprite_groups import SpriteGroups

#: Window sizes worth a row: 16:9, 16:10, 21:9 and 4K.
WINDOWS = [(1280, 720), (1920, 1080), (2560, 1440), (3440, 1440), (3840, 2160)]
SCALES = (1, 2, 3)
FRAME_BUDGET_MS = 1000.0 / 60


class Tile(pygame.sprite.Sprite):
    """Terrain: an image and a rect, no gameplay state."""

    def __init__(self, x: float, y: float, size: int = 64) -> None:
        super().__init__()
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        self.image.fill((80, 120, 80, 255))
        self.rect = pygame.FRect(x, y, size, size)


def make_renderer(scale: int) -> tuple[Renderer, SpriteGroups]:
    """A renderer on a real level, or a synthetic one when the assets are absent.

    The real level is what the numbers should mean, but ``assets/`` is
    git-ignored, so the benchmark falls back rather than refusing to run.
    """
    viewport = Viewport(DEFAULT_FRAMING, scale)
    viewport.surface.fill((24, 28, 36))
    camera = Camera(DEFAULT_FRAMING)
    renderer = Renderer(viewport.surface, camera)
    groups = SpriteGroups()
    for i in range(40):
        for j in range(40):
            groups.all_sprites.add(Tile(i * 64.0, j * 64.0))
    return renderer, groups


def _median_ms(action, repeats: int) -> float:
    action()
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        action()
        samples.append((perf_counter() - started) * 1000.0)
    return statistics.median(samples)


def measure_world_draw(scale: int, repeats: int) -> float:
    renderer, groups = make_renderer(scale)
    renderer.camera.set_world_size(40 * 64, 40 * 64)
    renderer.camera.offset.update(200.0, 100.0)
    return _median_ms(lambda: renderer.draw(groups, alpha=0.5), repeats)


def measure_presentation(target: int, window: tuple[int, int], repeats: int) -> tuple[float, float]:
    """Return (smooth, nearest) for one target-to-window pair."""
    source = pygame.Surface(target)
    source.fill((24, 28, 36))
    destination = pygame.Surface(window)
    smooth = _median_ms(lambda: pygame.transform.smoothscale(source, window, destination), repeats)
    nearest = _median_ms(lambda: pygame.transform.scale(source, window, destination), repeats)
    return smooth, nearest


def measure_level_load(repeats: int) -> str:
    """Whether the real level can be built here, for the report's header."""
    try:
        from src.core.level.level_manager import LEVEL_PATHS, LevelManager

        data = LevelManager(LEVEL_PATHS).get(0)
    except (OSError, FileNotFoundError, KeyError) as error:
        return f"unavailable ({type(error).__name__})"
    viewport = Viewport(DEFAULT_FRAMING, 2)
    Level(viewport.surface, data, InputManager())
    return f"{data.width}x{data.height} tiles, {data.pixel_width:.0f}x{data.pixel_height:.0f} px"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=40, help="samples per measurement")
    parser.add_argument("--window", type=int, nargs=2, metavar=("W", "H"), default=None)
    arguments = parser.parse_args()

    pygame.init()
    pygame.display.set_mode((320, 240))
    print(f"p pygame-ce {pygame.version.ver}, budget {FRAME_BUDGET_MS:.1f} ms at 60Hz")
    print(f"p framing {DEFAULT_FRAMING.width:.0f}x{DEFAULT_FRAMING.height:.0f}")
    print(f"p registered level: {measure_level_load(1)}")

    print("\n-- world draw, by render scale (pixels scale with the target) --")
    print(f"{'scale':>6}{'target':>14}{'draw ms':>10}")
    draws: dict[int, float] = {}
    for scale in SCALES:
        draws[scale] = measure_world_draw(scale, arguments.repeats)
        target = (
            f"{DEFAULT_FRAMING.viewport_size(scale)[0]}x{DEFAULT_FRAMING.viewport_size(scale)[1]}"
        )
        print(f"{scale:>6}{target:>14}{draws[scale]:>10.2f}")

    windows = [tuple(arguments.window)] if arguments.window else WINDOWS
    print("\n-- presentation, by window (independent of the render scale) --")
    print(f"{'window':>14}{'smooth':>10}{'nearest':>10}{'+ draw(2x)':>13}{'% budget':>11}")
    for window in windows:
        smooth, nearest = measure_presentation(
            DEFAULT_FRAMING.viewport_size(2), window, arguments.repeats
        )
        total = smooth + draws[2]
        print(
            f"{window[0]}x{window[1]:<8}{smooth:>9.2f} {nearest:>9.2f} "
            f"{total:>12.2f} {100 * total / FRAME_BUDGET_MS:>10.0f}%"
        )

    print(
        "\nThe last column is smooth scaling plus a 2x world draw. Nearest is the\n"
        "way to buy the difference back when a large window does not fit the budget."
    )


if __name__ == "__main__":
    main()
