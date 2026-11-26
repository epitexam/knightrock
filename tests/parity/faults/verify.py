"""Verify that every fault in the catalogue is detected by the parity suite.

The faults are applied in a temporary git worktree, never in the working tree.
Run from the repository root::

    python -m tests.parity.faults.verify

Exit code 0 means 12/12 killed; 1 means at least one fault survived.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.parity.faults.catalog import FAULTS
from tests.parity.scenarios.simulation import SCENARIOS

ROOT = Path(__file__).resolve().parents[3]


def _runner(root: Path, scenario: str) -> str:
    env = os.environ.copy()
    env.update(
        SDL_VIDEODRIVER="dummy",
        SDL_AUDIODRIVER="dummy",
        KNIGHTROCK_ARCH="legacy",
        PYTHONPATH=str(root),
        # A fault and its restoration can have the same size and the same
        # mtime (whole seconds); a stale .pyc would then keep the mutation
        # alive after the source was restored and make results nondeterministic.
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = subprocess.run(
        [sys.executable, "-m", "tests.parity.runner", "--scenario", scenario],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert len(lines) == 1, result.stdout
    return json.loads(lines[0])["digest"]


def main() -> int:
    baselines = {name: _runner(ROOT, name) for name in SCENARIOS}
    survivors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="knightrock-faults-") as temp:
        worktree = Path(temp) / "wt"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        try:
            # The parity package may still be untracked; make sure the worktree
            # runs exactly the suite that is being validated.
            shutil.copytree(ROOT / "tests/parity", worktree / "tests/parity", dirs_exist_ok=True)
            for fault in FAULTS:
                path = worktree / fault.path
                original = path.read_text(encoding="utf-8")
                if original.count(fault.old) != 1:
                    survivors.append(f"{fault.name}: pattern not found exactly once")
                    continue
                path.write_text(original.replace(fault.old, fault.new), encoding="utf-8")
                try:
                    killed = any(
                        _runner(worktree, name) != baseline for name, baseline in baselines.items()
                    )
                except subprocess.CalledProcessError as error:
                    killed = True  # a fault that crashes the sim cannot pass silently
                    print(
                        f"  {fault.name}: crash counted as killed\n{error.stderr}", file=sys.stderr
                    )
                finally:
                    path.write_text(original, encoding="utf-8")
                print(f"  {fault.name}: {'killed' if killed else 'SURVIVED'}")
                if not killed:
                    survivors.append(fault.name)
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )

    print(f"{len(FAULTS) - len(survivors)}/{len(FAULTS)} faults killed")
    if survivors:
        print("survivors: " + ", ".join(survivors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
