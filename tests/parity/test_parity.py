"""Parity checks: same script, two isolated processes, identical digest.

During Phase 0 both arches resolve to the legacy modules, so these tests are
a sanity check of the harness. As capabilities migrate, ``impl.NEW_PATHS``
grows and the same tests become the gate that must pass before a tranche is
allowed to contract its old path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.parity.scenarios.simulation import SCENARIOS

SCENARIO_NAMES = tuple(SCENARIOS)


def _run(scenario: str, arch: str, sandbox: Path) -> str:
    env = os.environ.copy()
    env.update(
        SDL_VIDEODRIVER="dummy",
        SDL_AUDIODRIVER="dummy",
        KNIGHTROCK_ARCH=arch,
        KNIGHTROCK_SAVE_DIR=str(sandbox),
        KNIGHTROCK_EXPORT_DIR=str(sandbox / "exports"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = subprocess.run(
        [sys.executable, "-m", "tests.parity.runner", "--scenario", scenario, "--arch", arch],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert len(lines) == 1, result.stdout
    return json.loads(lines[0])["digest"]


@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
def test_legacy_is_deterministic(scenario: str, tmp_path: Path) -> None:
    assert _run(scenario, "legacy", tmp_path) == _run(scenario, "legacy", tmp_path)


@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
def test_candidate_matches_legacy(scenario: str, tmp_path: Path) -> None:
    assert _run(scenario, "new", tmp_path) == _run(scenario, "legacy", tmp_path)


def test_scenarios_are_distinct(tmp_path: Path) -> None:
    digests = {_run(name, "legacy", tmp_path) for name in SCENARIO_NAMES}
    assert len(digests) == len(SCENARIO_NAMES)
