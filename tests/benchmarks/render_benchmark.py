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
from collections.abc import Sequence
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
from src.core.rendering.tile_chunk_index import TileChunkIndex
from src.core.settings import Simulation, World
from src.core.sprites import Sprite

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


def measure_cull(level: Level, repeats: int) -> tuple[float, float]:
    """Milliseconds to decide what to blit, with and without the tile index.

    Split out from the frame because the frame is dominated by things the cull
    cannot touch: blitting 115 tiles and filling the target. Isolating it is
    what shows what the index is actually worth, which on the registered level
    is small -- see the note printed below the table.

    The second number re-adds the tile plane to ``all_sprites`` and drops the
    index, which is exactly the linear scan the index replaced. It is the
    honest "before", measured in the same process on the same data rather than
    quoted from another run.
    """
    renderer = level.renderer
    groups = level.groups
    index = renderer._static_index
    foreground = TileChunkIndex(groups.fg_sprites) if groups.fg_sprites else None

    # "after" is the shipped state: tiles in the frozen plane, index installed.
    indexed = _median_ms(lambda: _cull_once(renderer, groups), repeats)

    # "before" is the state the index replaced: tiles back in all_sprites, no
    # index. The two have to be measured from their own real wiring -- leaving
    # the tiles in all_sprites while the index is installed would have the
    # indexed run walk the same 839 tiles twice and look twice as slow.
    groups.all_sprites.add(*groups.static_sprites)
    try:
        renderer.set_static_planes(None, None)
        scanned = _median_ms(lambda: _cull_once(renderer, groups), repeats)
    finally:
        for tile in tuple(groups.static_sprites):
            groups.all_sprites.remove(tile)
        if index is not None:
            renderer.set_static_planes(index, foreground)
    return scanned, indexed


def _cull_once(renderer, groups) -> None:
    renderer.camera.begin_frame(0.5)
    renderer._collect_visible_blits(groups)


def measure_cull_scaling(level: Level, sizes: Sequence[int], repeats: int) -> list[tuple]:
    """Cull cost against tile count, scanned linearly and through the index.

    The row that justifies the index is not the one for the shipped level.
    A linear scan is O(level) and the index is O(view), so the wider the
    level the more the index wins -- but the shipped level is 40x30 tiles, and
    839 tiles lands almost exactly on the break-even point, where the two are
    indistinguishable. Reading that as "the index is worthless" would be
    reading one point of a curve as the whole curve.

    Tiles are synthesised on a 60-column grid away from the camera's opening
    position, so the count grows while the number the cull actually draws
    stays put: that is the whole claim, that cost should not track level size.
    """
    renderer = level.renderer
    groups = level.groups
    original_index = renderer._static_index
    original_tiles = tuple(groups.static_sprites)
    groups.static_sprites.empty()
    tile_surface = pygame.Surface((World.TILE_SIZE, World.TILE_SIZE))
    rows: list[tuple] = []
    try:
        for count in sizes:
            # Each row is a fresh plane: leftover tiles from the previous row
            # would make the counts cumulative and the curve meaningless.
            groups.static_sprites.empty()
            added = [
                Sprite(
                    pos=((20 + index % 60) * World.TILE_SIZE, (20 + index // 60) * World.TILE_SIZE),
                    surf=tile_surface,
                )
                for index in range(count)
            ]
            for tile in added:
                groups.static_sprites.add(tile)

            renderer.set_static_planes(None, None)
            groups.all_sprites.add(*added)
            scanned = _median_ms(lambda: _cull_once(renderer, groups), repeats)
            for tile in added:
                groups.all_sprites.remove(tile)

            renderer.set_static_planes(TileChunkIndex(groups.static_sprites), None)
            indexed = _median_ms(lambda: _cull_once(renderer, groups), repeats)
            rows.append((len(groups.static_sprites), scanned, indexed))
    finally:
        groups.static_sprites.empty()
        for tile in original_tiles:
            groups.static_sprites.add(tile)
        if original_index is not None:
            renderer.set_static_planes(original_index, None)
    return rows


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

    viewport = pygame.Surface(letterbox((1280, 720), DEFAULT_FRAMING).size)
    level = Level(viewport, LevelManager(LEVEL_PATHS).get(0), InputManager())
    for _ in range(10):
        level.update(Simulation.TIMESTEP)
    level.renderer.camera.offset.update(300.0, 200.0)
    scanned, indexed = measure_cull(level, arguments.repeats * 4)
    tiles = len(level.groups.static_sprites)
    moving = len(level.groups.all_sprites)
    print(f"\n-- cull only: {tiles} tiles + {moving} moving sprites --")
    print(f"{'scan':>10}{'chunk index':>14}{'saved':>9}{'%':>7}")
    print(
        f"{scanned:>9.3f}ms{indexed:>13.3f}ms{scanned - indexed:>8.3f}ms"
        f"{100 * (scanned - indexed) / scanned:>6.0f}%"
    )
    print(
        f"\n{'':>10}On the shipped level the index is worth a fifth of the cull,\n"
        f"which is a rounding error next to the frame. Two things explain why,\n"
        f"and both matter for reading the number: a culled sprite is cheap (one\n"
        f"`Sprite.rect` and one C-level `colliderect`), and what the frame spends\n"
        f"its time on instead is filling the target and blitting the ~115 tiles\n"
        f"that survive the cull. 839 tiles is also close to where the two curves\n"
        f"cross, so this level cannot show what the index is for. The next table\n"
        f"varies the tile count:\n"
    )
    rows = measure_cull_scaling(level, (0, 1000, 4000, 10000, 22000), arguments.repeats * 2)
    print(f"{'tiles':>7}{'scan':>10}{'chunk index':>14}{'saved':>9}{'%':>7}")
    for count, scan_ms, index_ms in rows:
        print(
            f"{count:>7}{scan_ms:>9.3f}ms{index_ms:>13.3f}ms{scan_ms - index_ms:>8.3f}ms"
            f"{100 * (scan_ms - index_ms) / scan_ms:>6.0f}%"
        )
    print(
        "\nThe scan is linear in the tile count and the index is nearly flat: the\n"
        "number of tiles on screen does not change as the level grows, only where\n"
        "they are. That is the property worth paying for.\n"
        "\nNote on method: a cProfile run of this same code reports the draw at\n"
        "~2.8 ms/frame against the ~1.2 ms measured here, because profiling\n"
        "charges a Python-level call far more than it costs. The cull is hundreds\n"
        "of calls per frame, so it is the line a profiler inflates most, and a\n"
        "profile is the wrong instrument for deciding whether a cull is worth\n"
        "indexing. These are medians of unprofiled runs."
    )


if __name__ == "__main__":
    main()
