"""Atomic JSON writes shared by the settings and progression stores.

Both files live in a user-owned directory that may be on a different machine
state than the game (a crash, a full disk, a power loss). Writing them in
place risks leaving a truncated file that the next launch reads as corruption.
This module owns the one implementation of the write-through-temporary
protocol, with a best-effort backup of the file being replaced.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _keep_backup(path: Path) -> None:
    """Copy the file about to be replaced next to it, best effort."""
    try:
        if path.is_file():
            shutil.copy2(path, path.with_suffix(".json.bak"))
    except OSError as error:
        logger.warning("Could not keep a backup of %s: %s", path, error)


def write_json_atomic(path: Path, data: Any, *, backup: bool = True) -> None:
    """Serialize ``data`` as indented JSON and replace ``path`` atomically.

    A failure anywhere in the serialization or the write removes the temporary
    file, so a caller that retries never finds a half-written file at ``path``
    or a leftover in the same directory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        _keep_backup(path)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(data, temporary, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
