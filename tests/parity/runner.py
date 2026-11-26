"""Run one parity scenario against one architecture and print a canonical line.

Usage::

    python -m tests.parity.runner --scenario melee --arch legacy
    python -m tests.parity.runner --scenario all --arch new

The runner is intentionally a process boundary: legacy and candidate never
share module-level state (``PROFILES``, ``shared_library()``, the gameplay-data
cache). The caller compares the two lines.
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  - drivers must be set before pygame is imported

from tests.parity.canonical import canonical_json, digest  # noqa: E402
from tests.parity.impl import ARCHES, current_arch  # noqa: E402
from tests.parity.scenarios.simulation import SCENARIOS  # noqa: E402


def run_one(name: str, arch: str) -> dict[str, object]:
    os.environ["KNIGHTROCK_ARCH"] = arch
    pygame.init()
    # The asset library converts frames to the display format; a dummy window
    # is enough and keeps the parity scenarios art-free.
    pygame.display.set_mode((320, 240))
    try:
        state = SCENARIOS[name]()
    finally:
        pygame.quit()
    return {
        "arch": arch,
        "scenario": name,
        "digest": digest(state),
        "state": state,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="all", choices=(*SCENARIOS, "all"))
    parser.add_argument("--arch", default=current_arch(), choices=ARCHES)
    parser.add_argument("--full", action="store_true", help="print the whole snapshot")
    args = parser.parse_args(argv)

    names = tuple(SCENARIOS) if args.scenario == "all" else (args.scenario,)
    for name in names:
        result = run_one(name, args.arch)
        if not args.full:
            result.pop("state")
        print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
