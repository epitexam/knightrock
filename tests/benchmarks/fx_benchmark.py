"""What one particle costs to build, and what the plane's geometry actually does.

The dust rework left the FX plane free of a per-frame allocation problem, so
this benchmark exists for the other direction: the *construction* cost, which is
where the plane still pays. A particle that builds its surface at construction
and then only moves and fades is cheap forever; one that rebuilds geometry is
expensive on the single frame it is born, and the budget it spends there is
taken straight out of the frame the player is on.

Three numbers, and each one has already changed a decision:

- **microseconds to construct**, per family. The reason the shatter arc came
  first is here: 1139 us against 71 us for a whole landing dust, on a 16.7 ms
  budget. Nothing else in the plane is close.
- **surfaces painted per N breaks.** This is a count, not a time, and it is the
  one that cannot be argued with: the shatter arc is a pure function of
  ``(progress, seed)``, so a grid of seeds bounds the geometry for the whole
  session. A per-spawn seed makes that count grow with the number of breaks.
- **samples per arc stroke**, against the number of degrees one pixel of arc
  covers at that radius. The stroke samples every half degree unconditionally,
  which is finer than the grid can show at every radius the plane uses.

Run it from the repo root::

    uv run python tests/benchmarks/fx_benchmark.py

Medians of unprofiled runs, per the rule in ``notes/audit_p1_measured.md``:
profiling charges a Python-level call far more than it costs, and every line
this plane draws with is one.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import time
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.core.colors import FXColors
from src.core.fx import (
    DashDustParticle,
    DizzyVortexParticle,
    DustParticle,
    FootstepDustParticle,
    GrainParticle,
    OrbitParticle,
    ShatterArcParticle,
    ShieldArcParticle,
    SweatParticle,
    clear_frame_cache,
    spawn_footstep_dust,
    spawn_footstep_grains,
    spawn_landing_dust,
    spawn_landing_grains,
    spawners,
)
from src.core.fx import particles as particles
from src.core.settings import Dust, FootstepDust, FxGuard

#: The frame this plane has to fit inside, at 60 Hz.
FRAME_BUDGET_US = 1000.0 / 60.0 * 1000.0

#: The arc stroke's sample step, in degrees, and the radii the plane asks for.
#: Reported rather than asserted: the number that matters is how much finer the
#: step is than a pixel can show, which is in ``arc_stroke_samples``.
ARC_STEP_DEGREES = 0.5
ARC_RADII = (6.0, 14.0, FxGuard.ARC_RADIUS, FxGuard.SHARD_RADIUS, 40.0)


def _median_us(action, repeats: int) -> float:
    """Microseconds per call, median of ``repeats`` batches.

    One batch of many calls rather than many batches of one, because a single
    ``perf_counter`` pair costs enough on the scale of these numbers to be the
    measurement.
    """
    action()
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(_BATCH):
            action()
        samples.append((time.perf_counter() - start) * 1e6 / _BATCH)
    return statistics.median(samples)


_BATCH = 30


def _entity(x: float = 100.0) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        hitbox=pygame.FRect(x, 36.0, 40, 48),
        velocity=pygame.math.Vector2(1100.0, 0.0),
        facing_right=True,
        landed_impact=0.0,
    )


def _landing() -> pygame.sprite.Group:
    group = pygame.sprite.Group()
    subject = _entity()
    spawn_landing_dust(group, subject, 1400.0)
    spawn_landing_grains(group, subject, 1400.0)
    return group


def _footstep() -> pygame.sprite.Group:
    """One footstep: the two sheets and the grit, as the emitter spends them.

    It is in the table next to ``_landing`` because those are the two events
    that lay a mark and its spray, and the footstep is the one that happens
    twelve times a second. The per-particle rows above are what the mark costs
    to build; this is what a step costs.
    """
    group = pygame.sprite.Group()
    subject = _entity()
    spawn_footstep_dust(group, subject, foot=False, tier=FootstepDust.DEFAULT_TIER)
    spawn_footstep_grains(group, subject)
    return group


def measure_construction(repeats: int) -> list[dict[str, object]]:
    """Microseconds to construct one particle, per family.

    Every family is built through its public constructor with the arguments the
    spawner would give it, because the cost that matters is the one the game
    pays and not the cost of a stripped-down instance.
    """
    clear_frame_cache()
    cases: tuple[tuple[str, object], ...] = (
        ("landing sheet", lambda: DustParticle((0.0, 0.0), (0.0, 0.0), radius=Dust.PUFF_RADIUS)),
        ("dash sheet", lambda: DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=8.0)),
        (
            "footstep sheet",
            lambda: FootstepDustParticle((0.0, 0.0), (0.0, 0.0)),
        ),
        ("whole footstep", lambda: _footstep()),
        ("grain", lambda: GrainParticle((0.0, 0.0), (0.0, 0.0), size=2, tint=0.1)),
        (
            "dizzy star",
            lambda: OrbitParticle(
                (0.0, 0.0),
                radius=10.0,
                phase=0.0,
                speed=1.0,
                color=FXColors.star,
                core=FXColors.star_core,
                ttl=1.0,
            ),
        ),
        ("dizzy swirl", lambda: DizzyVortexParticle((0.0, 0.0), ttl=1.0)),
        ("sweat drop", lambda: SweatParticle((0.0, 0.0), (0.0, 0.0))),
        ("block ring", lambda: ShieldArcParticle((0.0, 0.0), 1.0)),
        ("shatter arc", lambda: ShatterArcParticle((0.0, 0.0), 1.0, seed=7)),
        (
            "whole landing",
            lambda: _landing(),
        ),
    )
    results = []
    for name, build in cases:
        cost = _median_us(build, repeats)
        results.append(
            {
                "name": name,
                "median_us": cost,
                "percent_of_frame": cost / FRAME_BUDGET_US * 100.0,
            }
        )
    return results


def measure_shard_surfaces(breaks: int) -> dict[str, object]:
    """How many distinct shard surfaces ``breaks`` breaks paint.

    The count, not the time, is the point: ``_shatter_step`` is a pure function
    of ``(progress, seed, side)`` and nothing else varies per spawn, so the
    geometry is bounded by the grid of layouts however many breaks go through
    it. A spawn that draws a fresh 16-bit seed per break is a per-break cost
    and this is the number that shows it.
    """
    clear_frame_cache()
    for _ in range(breaks):
        for side in (1.0, -1.0):
            ShatterArcParticle((0.0, 0.0), side, seed=spawners._fx_rng.randrange(1 << 16))
    held = len(particles._shard_cache)
    return {
        "breaks": breaks,
        "spawned": breaks * 2,
        "ladder_entries": held,
        "surfaces": sum(len(steps) for steps in particles._shard_cache.values()),
        "grid_bound": 2 * FxGuard.SHARD_SEEDS,
    }


def arc_stroke_samples() -> list[dict[str, object]]:
    """The arc stroke's sample count against what a pixel can resolve.

    One pixel of arc is ``360 / (2*pi*r)`` degrees. Sampling finer than that
    costs interpreted trig per sample and changes no pixel, so the ratio is the
    waste factor at that radius.
    """
    rows = []
    for radius in ARC_RADII:
        pixel = 360.0 / (2.0 * math.pi * radius)
        rows.append(
            {
                "radius": radius,
                "degrees_per_pixel": pixel,
                "step_degrees": ARC_STEP_DEGREES,
                "waste_factor": pixel / ARC_STEP_DEGREES,
            }
        )
    return rows


def run_benchmark(*, repeats: int = 5, breaks: int = 20) -> dict[str, object]:
    pygame.init()
    pygame.display.set_mode((64, 64))
    return {
        "schema": 1,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "frame_budget_us": FRAME_BUDGET_US,
        "construction": measure_construction(repeats),
        "shard_surfaces": measure_shard_surfaces(breaks),
        "arc_stroke": arc_stroke_samples(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--breaks", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmark(repeats=args.repeats, breaks=args.breaks)
    serialized = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
