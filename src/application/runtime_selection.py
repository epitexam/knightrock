"""Select the application implementation from ``KNIGHTROCK_ARCH``.

After the cutover (ADR 0001, Phase 5) both values resolve to the same
implementation: ``Game`` is the composition root of the target architecture.
The flag is kept as a harmless compatibility knob so an old launch command
still works, and so the parity runner can keep its two-process comparison.
"""

from __future__ import annotations

import os
from typing import Any

LEGACY = "legacy"
NEW = "new"


def game_class(legacy: type[Any], arch: str | None = None) -> type[Any]:
    """Return the Game implementation for ``arch`` (both spellings work)."""
    chosen = arch if arch is not None else os.environ.get("KNIGHTROCK_ARCH", NEW)
    if chosen not in (LEGACY, NEW):
        raise ValueError(f"unknown KNIGHTROCK_ARCH {chosen!r}; expected {LEGACY!r} or {NEW!r}")
    return legacy
