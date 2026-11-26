"""Legacy core/entities/states/data paths stay pure re-exports during Phase 4."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

CANDIDATES = {
    f"src.simulation.{p.stem}"
    for p in (
        SRC / "simulation/sprites.py",
        SRC / "simulation/sprite_groups.py",
        SRC / "simulation/hazards.py",
        SRC / "simulation/object_pool.py",
        SRC / "simulation/settings.py",
        SRC / "simulation/atomic_json.py",
    )
}
for sub in ("entities", "states", "data", "ecs", "level", "rollback", "animation"):
    CANDIDATES.add(f"src.simulation.{sub}")
    CANDIDATES |= {
        "src.simulation." + ".".join(p.relative_to(SRC / "simulation").with_suffix("").parts)
        for p in (SRC / "simulation" / sub).rglob("*.py")
    }
CANDIDATES |= {"src.platform.assets", "src.platform.resource_coordinator"}
CANDIDATES |= {
    f"src.shared.{name}"
    for name in (
        "events",
        "paths",
        "colors",
        "input_actions",
        "input_state",
        "state_names",
        "damage_types",
    )
}


def test_legacy_simulation_modules_only_reexport_candidates() -> None:
    paths = [
        *(SRC / "entities").rglob("*.py"),
        *(SRC / "states").rglob("*.py"),
        *(SRC / "data").rglob("*.py"),
        *(SRC / "core/ecs").rglob("*.py"),
        *(SRC / "core/level").rglob("*.py"),
        *(SRC / "core/rollback").rglob("*.py"),
        *(SRC / "core/animation").rglob("*.py"),
        SRC / "core/sprites.py",
        SRC / "core/sprite_groups.py",
        SRC / "core/hazards.py",
        SRC / "core/object_pool.py",
        SRC / "core/settings.py",
        SRC / "core/atomic_json.py",
        SRC / "core/asset_library.py",
        SRC / "core/resource_coordinator.py",
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
