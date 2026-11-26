"""Select the application implementation from ``KNIGHTROCK_ARCH``.

This is the single strangler seam: the entry point keeps calling a class named
``Game``, while the environment decides which implementation backs it. Legacy
is the default until the final cutover (ADR 0001, Phase 5).

The selector takes the legacy class as a parameter instead of importing it so
the entry point's ``Game`` symbol remains patchable by tests.
"""

from __future__ import annotations

import os
from typing import Any

LEGACY = "legacy"
NEW = "new"


def game_class(legacy: type[Any], arch: str | None = None) -> type[Any]:
    """Return the Game implementation for ``arch``.

    ``new`` raises until the candidate application package exists; a missing
    candidate must be a loud startup error, never a silent fallback to legacy.
    """
    chosen = arch if arch is not None else os.environ.get("KNIGHTROCK_ARCH", LEGACY)
    if chosen == LEGACY:
        return legacy
    if chosen == NEW:
        raise RuntimeError(
            "KNIGHTROCK_ARCH=new is not available yet: the candidate application "
            "package lands in Phase 1 of ADR 0001"
        )
    raise ValueError(f"unknown KNIGHTROCK_ARCH {chosen!r}; expected {LEGACY!r} or {NEW!r}")
