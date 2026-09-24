"""Repeatable contact-pipeline benchmark for the O4 baseline."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    # Support ``python tests/benchmarks/contact_benchmark.py`` from the repo root.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.combat.frame_data import HitProperties
from src.combat.knockback import KnockbackConfig
from src.core.level.systems.contact_system import ContactSystem, OffensiveBox
from src.physics.entity_grid import EntityGrid
from tests.unit.helpers import activate, entity_at, make_attack, make_phase


@dataclass(frozen=True)
class Scenario:
    size: int
    use_grid: bool
    system: ContactSystem
    boxes: tuple[OffensiveBox, ...]
    targets: tuple[object, ...]
    grid: EntityGrid | None


def build_scenario(size: int, *, use_grid: bool) -> Scenario:
    """Build one dense roster with the historical 1/16/64 pair counts."""
    definition = make_attack(
        make_phase(
            startup=1,
            active=8,
            recovery=1,
            size=(200.0, 200.0),
            offset=(0.0, 0.0),
        )
    )
    attackers = tuple(entity_at(0.0, faction="A", definition=definition) for _ in range(size))
    targets = tuple(entity_at(0.0, faction="B") for _ in range(size))
    for attacker in attackers:
        activate(attacker)
    boxes = tuple(
        OffensiveBox(
            box=attacker.combat.attack_boxes[0],
            swept=attacker.combat.swept_attack_boxes,
            hit=HitProperties(damage=1.0, knockback=KnockbackConfig(power=(0.0, 0.0))),
            faction="A",
            owner_id=attacker.id,
            can_contact=lambda _target_id: True,
            kind="melee",
            attacker=attacker,
        )
        for attacker in attackers
    )
    grid = EntityGrid() if use_grid else None
    if grid is not None:
        grid.rebuild(targets)
    return Scenario(size, use_grid, ContactSystem(), boxes, targets, grid)


def run_once(scenario: Scenario) -> int:
    """Run one measured pass and return the contact count."""
    for target in scenario.targets:
        target.vitals.reset()
    outcome = scenario.system.resolve(scenario.boxes, scenario.targets, scenario.grid)
    return outcome.metrics.contacts


def run_benchmark(*, iterations: int = 300, repeats: int = 5) -> dict[str, object]:
    """Measure dense 1v1, 4v4 and 8v8 rosters with and without the grid."""
    results: list[dict[str, object]] = []
    for size in (1, 4, 8):
        for use_grid in (False, True):
            scenario = build_scenario(size, use_grid=use_grid)
            for _ in range(5):
                run_once(scenario)
            samples: list[float] = []
            contacts = 0
            for _ in range(repeats):
                start = time.perf_counter()
                for _ in range(iterations):
                    contacts = run_once(scenario)
                elapsed = (time.perf_counter() - start) * 1000.0
                samples.append(elapsed / iterations)
            results.append(
                {
                    "name": f"{size}v{size}-{'grid' if use_grid else 'exhaustive'}",
                    "pairs_tested": size * size,
                    "contacts": contacts,
                    "median_ms_per_tick": statistics.median(samples),
                    "min_ms_per_tick": min(samples),
                    "max_ms_per_tick": max(samples),
                }
            )
    return {
        "schema": 1,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "iterations": iterations,
        "repeats": repeats,
        "scenarios": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmark(iterations=args.iterations, repeats=args.repeats)
    serialized = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
