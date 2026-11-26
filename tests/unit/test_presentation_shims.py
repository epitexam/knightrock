"""Legacy display/rendering/fx/ui paths must stay pure re-exports."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

CANDIDATES = {
    f"src.presentation.{sub}" for sub in ("display", "rendering", "fx", "ui", "ui.world_overlay")
}
CANDIDATES |= {
    f"src.presentation.{sub}.{p.stem}"
    for sub in ("display", "rendering", "fx")
    for p in (SRC / "presentation" / sub).glob("*.py")
}
CANDIDATES |= {
    "src.presentation.ui." + ".".join(p.relative_to(SRC / "presentation/ui").with_suffix("").parts)
    for p in (SRC / "presentation/ui").rglob("*.py")
}


def test_legacy_presentation_modules_only_reexport_candidates() -> None:
    paths = [
        *(SRC / "core/display").rglob("*.py"),
        *(SRC / "core/rendering").rglob("*.py"),
        *(SRC / "core/fx").rglob("*.py"),
        *(SRC / "ui").rglob("*.py"),
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert imported <= CANDIDATES, (
            f"{path.relative_to(SRC)} imports outside the candidate tree: {sorted(imported)}"
        )
