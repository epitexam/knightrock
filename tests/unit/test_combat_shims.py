"""The legacy combat path must stay a pure re-export during migration."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def test_legacy_combat_modules_only_reexport_the_candidate() -> None:
    candidates = {
        f"src.simulation.combat.{other.stem}" for other in (SRC / "simulation/combat").glob("*.py")
    }
    for path in sorted((SRC / "combat").glob("*.py")):
        if path.name == "damage_types.py":
            # Already part of the shared kernel, not a combat module.
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert imported <= candidates, (
            f"{path.name} imports outside the candidate tree: {sorted(imported)}"
        )
