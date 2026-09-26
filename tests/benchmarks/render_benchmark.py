"""What one presented frame costs, split into the parts that are now separate.

Run it from the repo root::

    uv run python tests/benchmarks/render_benchmark.py

Two numbers decide things, and neither could be measured before this rework:

- **the presentation is a 1:1 blit.** There is no resampling left to pay for, so
  a window of any size costs the same handful of milliseconds it takes to copy a
  frame, and the picture is exactly the picture. What used to be measured here --
  ``smoothscale`` from a fixed target onto the window, 3.95 ms at 1280x720 rising
  to 13.32 ms at 4K -- is gone, and gone for a reason that was a *correctness*
  problem before it was a performance one: a resampled frame is a soft one, and
  no setting could fix it because the ratio was not the game's to choose.
- **the world draw is a function of the target, and the target is the window.**
  So a bigger window costs more fill, and that is not a setting any more: it is
  the window the player has.

The dummy SDL driver has no fast renderer, so these are CPU-only figures, which
is representative for the scaling pygame does on the CPU for a software surface
whether or not a GPU is present. It understates a real window's compositing. The
ratios between rows are the actionable part.
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
from src.core.display.letterbox import letterbox
from src.core.display.presentation import Presentation
from src.core.input.input_manager import InputManager
from src.core.level.level import Level
from src.core.level.level_manager import LEVEL_PATHS, LevelManager
from src.core.settings import Simulation

#: Window sizes worth a row: the common ones, 16:10, ultrawide and 4K.
WINDOWS = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3440, 1440), (3840, 2160)]
FRAME_BUDGET_MS = 1000.0 / 60


def _median_ms(action, repeats: int) -> float:
    action()
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        action()
        samples.append((perf_counter() - started) * 1000.0)
    return statistics.median(samples)


def measure_world_draw(window: tuple[int, int], repeats: int) -> tuple[float, int]:
    """Milliseconds to draw the real level into the target a window asks for.

    Returns the cost and the density, because the second explains the first: the
    draw scales with the pixels, and the pixels are the window.
    """
    size = letterbox(window, DEFAULT_FRAMING).size
    viewport = pygame.Surface(size)
    level = Level(viewport, LevelManager(LEVEL_PATHS).get(0), InputManager())
    for _ in range(10):
        level.update(Simulation.TIMESTEP)
    renderer = level.renderer
    renderer.camera.offset.update(300.0, 200.0)
    return (
        _median_ms(lambda: renderer.draw(level.groups, alpha=0.5), repeats),
        renderer.camera.density,
    )


def measure_present(window: tuple[int, int], repeats: int) -> float:
    """Milliseconds to put a finished frame on a window of that size.

    The bars are filled and the frame is blitted, with no scaling anywhere: this
    is the number that used to depend on the ratio between a fixed target and the
    window, and it now only depends on how many pixels have to be written.
    """
    stage = pygame.Surface(window)
    presentation = Presentation(stage, DEFAULT_FRAMING)
    presentation.surface.fill((24, 28, 36))

    def present() -> None:
        for bar in presentation.bars:
            stage.fill((0, 0, 0), bar)
        stage.blit(presentation.surface, presentation.rect)
        pygame.display.flip()

    return _median_ms(present, repeats)


def measure_frame(window: tuple[int, int], repeats: int, *, pixel_perfect: bool) -> float:
    """Milliseconds for a whole presented frame at that window.

    Both halves, because either one alone is misleading: whole-pixel art shrinks
    the picture, so it makes the draw cheaper *and* the present no dearer, and a
    table that reported only the second would sell it as free.
    """
    stage = pygame.Surface(window)
    presentation = Presentation(stage, DEFAULT_FRAMING, pixel_perfect=pixel_perfect)
    size = presentation.surface.get_size()
    viewport = pygame.Surface(size)
    level = Level(viewport, LevelManager(LEVEL_PATHS).get(0), InputManager())
    for _ in range(10):
        level.update(Simulation.TIMESTEP)
    renderer = level.renderer
    renderer.camera.offset.update(300.0, 200.0)
    presentation.surface.fill((24, 28, 36))

    def present() -> None:
        for bar in presentation.bars:
            stage.fill((0, 0, 0), bar)
        stage.blit(presentation.surface, presentation.rect)
        pygame.display.flip()

    return _median_ms(lambda: (renderer.draw(level.groups, alpha=0.5), present()), repeats)


def measure_level_load() -> str:
    """Whether the real level can be built here, for the report's header."""
    try:
        data = LevelManager(LEVEL_PATHS).get(0)
    except (OSError, FileNotFoundError, KeyError) as error:
        return f"unavailable ({type(error).__name__})"
    viewport = pygame.Surface(letterbox((1280, 720), DEFAULT_FRAMING).size)
    Level(viewport, data, InputManager())
    return f"{data.width}x{data.height} tiles, {data.pixel_width:.0f}x{data.pixel_height:.0f} px"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=30, help="samples per measurement")
    parser.add_argument("--window", type=int, nargs=2, metavar=("W", "H"), default=None)
    arguments = parser.parse_args()

    pygame.init()
    pygame.display.set_mode((320, 240))
    print(f"p pygame-ce {pygame.version.ver}, budget {FRAME_BUDGET_MS:.1f} ms at 60Hz")
    print(f"p framing {DEFAULT_FRAMING.width:.0f}x{DEFAULT_FRAMING.height:.0f} world units")
    print(f"p registered level: {measure_level_load()}")

    windows = [tuple(arguments.window)] if arguments.window else WINDOWS
    print("\n-- one presented frame, by window (the target *is* the window) --")
    print(
        f"{'window':>14}{'target':>14}{'density':>9}{'world':>8}{'present':>9}"
        f"{'frame':>8}{'%':>6}{'whole-px':>10}{'%':>6}"
    )
    for window in windows:
        draw, density = measure_world_draw(window, arguments.repeats)
        present = measure_present(window, arguments.repeats)
        size = letterbox(window, DEFAULT_FRAMING).size
        total = draw + present
        whole = measure_frame(window, arguments.repeats, pixel_perfect=True)
        print(
            f"{window[0]}x{window[1]:<7}{size[0]}x{size[1]:<8}{density:>9.3f}{draw:>8.2f}"
            f"{present:>9.2f}{total:>8.2f}{100 * total / FRAME_BUDGET_MS:>5.0f}%"
            f"{whole:>10.2f}{100 * whole / FRAME_BUDGET_MS:>5.0f}%"
        )

    print(
        "\n`present` is a 1:1 blit plus the bars: there is no resample left to\n"
        "buy back, at any window size, and the picture is exactly the picture.\n"
        "`whole-px` is the whole frame with whole-pixel art on -- a smaller target,\n"
        "so a cheaper draw and a letterboxed one. The world draw is the only term\n"
        "that grows with the window, and it grows because the window is bigger:\n"
        "showing 1152x648 world units across a 4K panel is 8.3 Mpx of blending,\n"
        "and no setting makes that cheaper except a smaller window."
    )


if __name__ == "__main__":
    main()
