"""Architecture resolver driven by ``KNIGHTROCK_ARCH``.

``legacy`` points at the current module tree. ``new`` points at the candidate
packages as they appear; during the early phases both resolve to the same
modules, which is what makes a legacy-vs-legacy run a valid sanity check of
the harness.

The resolver is deliberately the *only* place that maps a logical capability
to a module path, so the runner never imports a concrete package by hand.
"""

from __future__ import annotations

import importlib
import os

LEGACY = "legacy"
NEW = "new"
ARCHES = (LEGACY, NEW)

#: Logical module names that have moved to the candidate tree. Entries are
#: added one capability at a time, only after that capability has passed the
#: parity check. The empty mapping is the Phase 0 state.
NEW_PATHS: dict[str, str] = {}


def current_arch() -> str:
    arch = os.environ.get("KNIGHTROCK_ARCH", LEGACY)
    if arch not in ARCHES:
        raise ValueError(f"unknown KNIGHTROCK_ARCH {arch!r}; expected one of {ARCHES}")
    return arch


def module_name(logical: str) -> str:
    """Resolve ``core.level.level`` to the importable module for this arch."""
    if current_arch() == NEW and logical in NEW_PATHS:
        return NEW_PATHS[logical]
    return f"src.{logical}"


def import_module(logical: str):  # type: ignore[no-untyped-def]
    return importlib.import_module(module_name(logical))
