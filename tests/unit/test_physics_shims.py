"""The legacy physics path must stay a pure re-export during migration."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_legacy_physics_modules_only_reexport_the_candidate() -> None:
    for path in sorted((SRC / "physics").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert imported <= {
            "src.simulation.physics",
            *(
                f"src.simulation.physics.{other.stem}"
                for other in (SRC / "simulation/physics").glob("*.py")
            ),
        }, f"{path.name} imports outside the candidate tree: {sorted(imported)}"
