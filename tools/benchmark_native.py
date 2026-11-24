"""A/B the compiled physics helpers against the same workload in pure Python.

    uv run python tools/build_native.py
    uv run python tools/benchmark_native.py --rounds 5

Each round runs both modes in a fresh process, in alternating order, so a warm
cache or a noisy neighbour cannot flatter whichever mode happens to go second.
The pure process gets a throwaway copy of the tree with every ``.so`` removed;
the native process uses the real tree. The workload's checksum must agree in
all runs: a faster mode that computes a different world is a bug, not a win.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = Path("tests/benchmarks/native_benchmark.py")


def _run(cwd: Path, iterations: int) -> dict[str, object]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(cwd)
    result = subprocess.run(
        [sys.executable, str(WORKLOAD), "--iterations", str(iterations)],
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    if not lines:
        raise RuntimeError(f"no measurement in:\n{result.stdout[-2000:]}")
    return json.loads(lines[-1])


def _pure_tree(temp: Path) -> Path:
    tree = temp / "pure"
    tree.mkdir()
    for entry in ("src", "tests"):
        shutil.copytree(
            ROOT / entry,
            tree / entry,
            ignore=shutil.ignore_patterns("*.so", "__pycache__", "*.pyc"),
        )
    shutil.copy(ROOT / "pyproject.toml", tree / "pyproject.toml")
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()

    if not any((ROOT / "src").rglob("*.so")):
        raise SystemExit("no native extensions found: run tools/build_native.py first")

    samples: dict[str, list[float]] = {"native": [], "pure": []}
    checksums: set[float] = set()
    with tempfile.TemporaryDirectory(prefix="knightrock-native-ab-") as scratch:
        pure = _pure_tree(Path(scratch))
        for round_number in range(args.rounds):
            order = ("native", "pure") if round_number % 2 == 0 else ("pure", "native")
            for mode in order:
                result = _run(ROOT if mode == "native" else pure, args.iterations)
                checksums.add(float(result["checksum"]))
                samples[mode].append(float(result["median_ms"]))
                print(
                    f"round {round_number + 1}: {mode:>6} "
                    f"{float(result['median_ms']):.3f} ms/iteration"
                )

    if len(checksums) != 1:
        raise SystemExit(f"the modes disagree on the world: {sorted(checksums)}")
    native = statistics.median(samples["native"])
    pure = statistics.median(samples["pure"])
    print(f"\nchecksum {checksums.pop():.3f} in all {args.rounds * 2} runs")
    print(f"native  {native:.3f} ms/iteration  {samples['native']}")
    print(f"pure    {pure:.3f} ms/iteration  {samples['pure']}")
    print(f"speedup {pure / native:.2f}x")


if __name__ == "__main__":
    main()
