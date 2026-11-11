"""The dependency direction between the layers, enforced.

`core` is the simulation and its drawing; `ui` is the interface; `application`
is the composition root that wires them together. The rules below are the ones
that hold today and are worth keeping, each with the reason it exists -- an
allowlist rather than a growing list of exceptions, because a rule with
exceptions is a rule nobody reads.

The concrete cost of not having them: `core/rendering/renderer.py` used to
construct a `UIManager`, so the renderer could not be built without a font
cache and a panel layout, and a test that wanted to know whether a tile was
culled had to stand up the whole interface to ask. The interface is now
injected through :mod:`src.core.rendering.overlay`.

These are checks rather than docstrings on purpose. A docstring is a claim; a
test is the thing that notices the next convenient import.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

#: The layers this file reasons about.
LAYERS = ("application", "combat", "core", "data", "entities", "physics", "states", "ui")

#: What a layer may reach outside itself, per layer and per module. Everything
#: absent is a violation, so widening a rule is a deliberate edit here.
#:
#: Only `core` has a rule: it is the simulation and its drawing, and the two
#: layers above it -- the interface and the application -- reach it by
#: injection and by subscription, never the other way round. The other layers
#: are not a strict hierarchy (`physics` reads `core.settings`, `states` reads
#: `core`), and a rule about an architecture the project does not have would be
#: noise.
ALLOWED_MODULES: dict[str, dict[str, frozenset[str]]] = {
    "core": {
        # The interface reaches `core` through src.core.rendering.overlay.
        "ui": frozenset(),
        # The simulation publishes facts on src.core.events and holds no
        # reference to the application.
        "application": frozenset(),
    },
}


#: Modules exempt from their layer's rule, with the reason.
#:
#: `core/game.py` is the composition root. It builds the scene stack, the event
#: bus and the audio bus, and hands them to the layers below; that is the one
#: job it has. It is named `core` for historical reasons and sits at the top of
#: the dependency graph, not the bottom.
EXEMPT: dict[str, str] = {
    "core/game.py": "the composition root: it wires the layers together",
}


def _layer_of(path: Path) -> str:
    return path.relative_to(SRC).parts[0]


def _imported_layers(path: Path) -> set[str]:
    """The layers this module imports from, by AST rather than by grep.

    A text search would match a layer name inside a docstring or a string --
    and this file's own docstring is full of them.
    """
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
            # `src.<layer>...` and a bare `<layer>` both count.
            if parts[0] == "src" and len(parts) >= 2:
                found.add(parts[1])
            elif parts[0] in LAYERS:
                found.add(parts[0])
    return found


def _imports(path: Path) -> set[str]:
    """Every dotted module name this file imports, as `src.x.y` or `x`."""
    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _violations(layer: str) -> list[str]:
    """Every import in this layer that its own rule does not allow."""
    allowed = ALLOWED_MODULES.get(layer)
    if allowed is None:
        return []
    offenders: list[str] = []
    for path in sorted((SRC / layer).rglob("*.py")):
        relative = str(path.relative_to(SRC))
        if relative in EXEMPT:
            continue
        for target in sorted(_imported_layers(path) - {layer}):
            permitted_modules = ALLOWED_MODULES.get(layer, {}).get(target)
            if permitted_modules is not None:
                for name in sorted(_imports(path)):
                    normalised = name.removeprefix("src.")
                    if not normalised.startswith(f"{target}."):
                        continue
                    module = normalised[len(target) + 1 :]
                    if module not in permitted_modules:
                        offenders.append(
                            f"{relative} -> {normalised} (only "
                            f"{', '.join(sorted(permitted_modules))} of {target} is allowed)"
                        )
            else:
                offenders.append(f"{relative} -> {target} (not permitted)")
    return offenders


def test_core_does_not_import_the_interface_layer() -> None:
    """The rule this branch was opened for."""
    offenders = [line for line in _violations("core") if "-> ui" in line]
    assert offenders == [], (
        "core must not import ui: the interface is injected through "
        "src.core.rendering.overlay.WorldOverlay, never constructed by core"
    )


def test_the_simulation_does_not_import_the_application() -> None:
    """The simulation talks to the application through src.core.events only.

    The level publishes facts on the bus and holds no reference to the
    application, which also keeps a rewind from re-emitting something the
    player already saw.
    """
    offenders = [line for line in _violations("core") if "-> application" in line]
    assert offenders == [], "core must not import application: publish on src.core.events"


def test_the_renderer_names_no_ui_module() -> None:
    """The specific inversion, named so a revert is obvious in the diff."""
    source = (SRC / "core/rendering/renderer.py").read_text(encoding="utf-8")
    assert "src.ui" not in source
    assert "UIManager" not in source


def test_the_interface_satisfies_the_overlay_port() -> None:
    """`UIManager` is the implementation; the port is checked against it here.

    Structural, at test time, because a Protocol nothing satisfies is a
    comment. `NullOverlay` is the other implementation and is the default, so
    both are checked.
    """
    from src.core.rendering.overlay import NullOverlay, WorldOverlay
    from src.ui.ui_manager import UIManager

    for implementation in (UIManager, NullOverlay):
        for method in WorldOverlay.__protocol_attrs__:
            assert callable(getattr(implementation, method, None)), (
                f"{implementation.__name__} does not satisfy WorldOverlay.{method}"
            )


def test_the_composition_root_is_exempt_on_purpose() -> None:
    """An exemption nobody notices is a hole; this one is asserted."""
    assert "application" in _imported_layers(SRC / "core/game.py")
    assert "core/game.py" in EXEMPT


def test_the_layer_walk_actually_finds_the_modules() -> None:
    """Guard the guard: an empty walk would make every rule above vacuous."""
    assert len(list((SRC / "core").rglob("*.py"))) > 40
    assert "ui" in _imported_layers(SRC / "ui/ui_manager.py")
    assert "core" in _imported_layers(SRC / "ui/ui_manager.py")


@pytest.mark.parametrize("layer", LAYERS)
def test_every_layer_is_a_directory_we_walked(layer: str) -> None:
    assert (SRC / layer).is_dir()
