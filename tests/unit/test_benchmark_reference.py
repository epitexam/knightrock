"""The feel benchmark can fail, now that its fighters are seeded.

Two processes used to disagree on these numbers: ``Entity`` built an unseeded
``Random`` and ``create_enemy`` had no way to pass one in. ``_arena`` now seeds
both fighters before the settling ticks (``combat_feel.SEED``), so a tuning
regression is visible here instead of being a diff a human has to notice.

The values are characterisation, not laws: a deliberate retune must update
them with a reason, the way the 0.088 -> 0.04 enemy hit-stop did in the audit.
Tolerances are wide on purpose -- the point is to catch a broken feel, not to
pin a platform's floating-point last digit.
"""

from __future__ import annotations

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from tests.benchmarks.combat_feel import measure  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    pygame.init()
    pygame.display.set_mode((64, 64))


@pytest.fixture(scope="module")
def report() -> dict[str, object]:
    return measure(2.0)


def test_enemy_warnings_are_exact(report: dict[str, object]) -> None:
    """Pure data, no RNG: a startup change must fail loudly."""
    assert report["enemy_warning_ms"] == {
        "goblin.claw_swipe": 267,
        "goblin.claw_reach": 367,
        "slime.body_slam": 333,
        "slime.slime_spit": 400,
        "tooth.bite": 200,
        "tooth.snap": 267,
        "shell.shell_bash": 367,
        "shell.shell_roll": 433,
    }


def test_hitstop_per_move_matches_the_tuning(report: dict[str, object]) -> None:
    """The dedicated 0.03-0.09 s player values, not the global formula."""
    duel = report["mash_slash_vs_target"]
    assert isinstance(duel, dict)
    assert duel["hitstop_by_move"] == pytest.approx(
        {
            "slash_high_1": 0.03,
            "slash_high_2": 0.03,
            "slash_high_3": 0.04,
            "slash_high_4": 0.09,
        },
        abs=0.005,
    )


def test_cancel_and_combo_stay_in_a_playable_band(report: dict[str, object]) -> None:
    duel = report["mash_slash_vs_target"]
    assert isinstance(duel, dict)
    assert 0.05 <= duel["cancel_success_ratio"] <= 0.30
    assert 5 <= duel["combo_peak"] <= 20


def test_frame_advantage_and_dodge_window_are_in_band(report: dict[str, object]) -> None:
    duel = report["mash_slash_vs_target"]
    assert isinstance(duel, dict)
    advantage = duel["frame_advantage"]
    assert isinstance(advantage, dict)
    assert advantage["hit"] == pytest.approx(14, abs=3)
    # The slower catalogue gives the dodge a longer lead before a blow lands.
    assert 0 <= report["perfect_dodge_ticks"] <= 12
