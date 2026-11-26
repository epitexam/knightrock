"""The optional mypyc tool must name modules that still exist.

A package move used to leave ``tools/build_native.py`` pointing at deleted
paths; ``--verify`` then failed with ``ModuleNotFoundError`` instead of the
expected "not native yet" error. Pinning the module list keeps the tool honest
without compiling anything.
"""

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_native.py"


def _modules() -> tuple[str, ...]:
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "MODULES" for target in node.targets
        ):
            return tuple(
                value.value
                for value in node.value.elts
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            )
    raise AssertionError("MODULES is no longer a literal tuple in build_native.py")


def test_native_module_paths_exist_and_import() -> None:
    modules = _modules()
    assert len(modules) == 5
    for path in modules:
        assert path.startswith("src/simulation/physics/"), path
        assert (ROOT / path).is_file(), path
        name = path.removesuffix(".py").replace("/", ".")
        assert importlib.util.find_spec(name) is not None, name
