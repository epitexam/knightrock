import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resource_path(relative_path: str | os.PathLike[str]) -> str:
    """Return an absolute resource path in development or a PyInstaller bundle."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    base_path = Path(bundle_root) if bundle_root is not None else PROJECT_ROOT
    return str((base_path / relative_path).resolve())
