"""Repository-wide conventions that no single module can enforce.

Formatting conventions (notably the Python 3.14 `except A, B:` spelling) are
owned by Ruff and checked by `ruff format --check` in CI. What remains here are
the cross-tree invariants Ruff cannot express: protocols must stay static so a
caller cannot branch on a structural match that `__getattr__` would fake.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = ("src", "tests", "tools")


def _python_files() -> list[Path]:
    """Every Python file the project maintains, minus caches and the venv."""
    found: list[Path] = []
    for root in SOURCE_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" not in path.parts:
                found.append(path)
    found.append(REPO_ROOT / "main.py")
    return sorted(found)


def test_game_protocols_are_not_runtime_checkable() -> None:
    """Protocols are for mypy; `isinstance` against them raises by design.

    A `runtime_checkable` protocol would let a caller branch on a structural
    match that cannot see attributes served by `__getattr__` -- which is how the
    wall-jump lock once passed every stand-in test while dead for the real
    player. The behaviour worth pinning is the TypeError, not the absence of a
    decorator string in a file.
    """
    from src.simulation.combat.combatant_protocol import AttackerPort
    from src.simulation.level.scene_host import SceneHost
    from src.simulation.physics.collisions import CollisionEntity

    for protocol in (AttackerPort, SceneHost, CollisionEntity):
        with pytest.raises(TypeError):
            isinstance(object(), protocol)


@pytest.mark.parametrize("root", SOURCE_ROOTS)
def test_every_source_root_exists(root: str) -> None:
    """The file walk above is only meaningful while the roots are real."""
    assert (REPO_ROOT / root).is_dir()


def test_the_file_walk_actually_finds_the_package() -> None:
    """Guard the guard: an empty walk would make the check vacuously true."""
    found = _python_files()
    assert len(found) > 100
    assert REPO_ROOT / "src" / "application" / "game.py" in found
