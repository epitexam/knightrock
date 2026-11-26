"""The migration is complete: the legacy package trees no longer exist.

Keeping this check after the cutover prevents a convenient import from
silently recreating one of the shims that carried the migration.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

LEGACY = (
    "core",
    "physics",
    "combat",
    "entities",
    "states",
    "data",
    "ui",
)

TARGETS = ("application", "platform", "presentation", "shared", "simulation")


def test_legacy_packages_are_gone() -> None:
    for name in LEGACY:
        assert not (SRC / name).exists(), f"legacy package src.{name} still exists"


def test_target_packages_are_present() -> None:
    for name in TARGETS:
        assert (SRC / name).is_dir(), f"target package src.{name} is missing"
