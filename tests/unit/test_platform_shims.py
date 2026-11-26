"""Legacy audio/input paths must stay pure re-exports during migration."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

CANDIDATES = {
    *(f"src.platform.input.{p.stem}" for p in (SRC / "platform/input").glob("*.py")),
    "src.shared.input_actions",
    "src.shared.input_state",
}


def test_legacy_input_and_audio_shims_only_reexport_candidates() -> None:
    paths = [SRC / "core/audio.py", *(SRC / "core/input").glob("*.py")]
    for path in paths:
        if path.name in ("__init__.py", "input_actions.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert imported <= CANDIDATES | {"src.platform.audio"}, (
            f"{path.name} imports outside the candidate tree: {sorted(imported)}"
        )
