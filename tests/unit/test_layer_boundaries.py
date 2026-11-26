"""The dependency direction between the layers, enforced.

After the cutover (ADR 0001) the five layers are ``application``,
``presentation``, ``platform``, ``shared`` and ``simulation``. ``application``
is the composition root; the other four never reach it. import-linter checks
the same rules across the whole graph, including indirect imports; these AST
tests keep the specific, historically expensive inversions named in code.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

LAYERS = ("application", "platform", "presentation", "shared", "simulation")

#: Only rules that are true today. Every absent target is a violation.
ALLOWED_MODULES: dict[str, dict[str, frozenset[str]]] = {
    "simulation": {"application": frozenset()},
    "presentation": {"application": frozenset()},
    "platform": {"application": frozenset()},
    "shared": {name: frozenset() for name in LAYERS if name != "shared"},
}


def _imported_layers(path: Path) -> set[str]:
    """Layers this module imports, by AST rather than by grep."""
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules = [node.module]
        for module in modules:
            parts = module.split(".")
            if parts[0] == "src" and len(parts) >= 2:
                found.add(parts[1])
            elif parts[0] in LAYERS:
                found.add(parts[0])
    return found


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _violations(layer: str) -> list[str]:
    allowed = ALLOWED_MODULES.get(layer, {})
    offenders: list[str] = []
    for path in sorted((SRC / layer).rglob("*.py")):
        relative = str(path.relative_to(SRC))
        for target in sorted(_imported_layers(path) - {layer}):
            permitted = allowed.get(target)
            if permitted is None:
                offenders.append(f"{relative} -> {target} (not permitted)")
                continue
            for name in sorted(_imports(path)):
                normalised = name.removeprefix("src.")
                if not normalised.startswith(f"{target}."):
                    continue
                module = normalised[len(target) + 1 :]
                if module not in permitted:
                    offenders.append(f"{relative} -> {normalised}")
    return offenders


@pytest.mark.parametrize("layer", ("simulation", "presentation", "platform", "shared"))
def test_no_layer_imports_the_composition_root(layer: str) -> None:
    offenders = [line for line in _violations(layer) if "-> application" in line]
    assert offenders == [], f"{layer} must not import application: {offenders}"


def test_the_renderer_names_no_ui_module() -> None:
    source = (SRC / "presentation/rendering/renderer.py").read_text(encoding="utf-8")
    assert "src.presentation.ui" not in source
    assert "UIManager" not in source


def test_the_interface_satisfies_the_overlay_port() -> None:
    from src.presentation.rendering.overlay import NullOverlay, WorldOverlay
    from src.presentation.ui.ui_manager import UIManager

    for implementation in (UIManager, NullOverlay):
        for method in WorldOverlay.__protocol_attrs__:
            assert callable(getattr(implementation, method, None)), (
                f"{implementation.__name__} does not satisfy WorldOverlay.{method}"
            )


def test_the_composition_root_lives_in_the_application() -> None:
    assert {"presentation", "simulation"} <= _imported_layers(SRC / "application/game.py")


def test_the_layer_walk_actually_finds_the_modules() -> None:
    assert len(list((SRC / "simulation").rglob("*.py"))) > 40
    assert "simulation" in _imported_layers(SRC / "presentation/ui/ui_manager.py")


@pytest.mark.parametrize("layer", LAYERS)
def test_every_layer_is_a_directory_we_walked(layer: str) -> None:
    assert (SRC / layer).is_dir()
