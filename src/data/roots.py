"""Where the gameplay data files live.

Its own module because both ``provider`` (which loads the files) and
``attack_data`` (which reads them) need the answer, and provider imports the
enemy schemas and the player config -- which need the attack tables. Resolving
the path from provider closes that loop, so it lives here instead.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from src.core.paths import resource_path

DATA_ROOT = "data"
GAMEPLAY_SUBDIR = "gameplay"


def gameplay_data_root(environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the directory holding ``gameplay/*.json``.

    ``KNIGHTROCK_DATA_DIR`` points the whole thing elsewhere, which is how
    modders and tests redirect it without touching the installed tree. The
    optional ``environ`` gives callers an explicit injection point.
    """
    env = os.environ if environ is None else environ
    override = env.get("KNIGHTROCK_DATA_DIR")
    base = Path(override) if override else Path(resource_path(DATA_ROOT))
    return base / GAMEPLAY_SUBDIR
