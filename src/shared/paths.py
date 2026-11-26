import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resource_path(relative_path: str | os.PathLike[str]) -> str:
    """Return an absolute resource path in development or a PyInstaller bundle."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    base_path = Path(bundle_root) if bundle_root is not None else PROJECT_ROOT
    return str((base_path / relative_path).resolve())


def confined_resource_path(relative_path: str | os.PathLike[str]) -> str:
    """Resolve a *data-supplied* path, refusing to escape the application root.

    :func:`resource_path` stays permissive on purpose: it also resolves paths
    assembled by the code and by tests (``AssetLibrary.frames()`` derives
    absolute frame paths from a directory it got here and passes them back to
    ``image()``). A path read from ``levels.json`` or ``enemies.json`` is a
    different matter -- it is editable input handed to PyTMX and to the image
    loader, so this companion function applies the trust boundary. Symlinks
    are resolved, so a link leading out of the root is refused as well.
    """
    bundle_root = getattr(sys, "_MEIPASS", None)
    base = (Path(bundle_root) if bundle_root is not None else PROJECT_ROOT).resolve()
    candidate = Path(relative_path)
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(
            f"Resource path {os.fspath(relative_path)!r} escapes the application root {str(base)!r}"
        )
    return str(resolved)
