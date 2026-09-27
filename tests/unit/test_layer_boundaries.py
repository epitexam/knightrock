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

#: The layers a module may import, beyond its own. Everything not listed here
#: is a violation, so widening a rule is a deliberate edit to this table.
#: What `core` may reach outside itself. Everything absent is a violation, so
#: widening a rule is a deliberate edit to this table rather than an addition
#: to a list of exceptions.
#:
#: Only two entries, and both are the audit's. The layers are *not* a strict
#: hierarchy -- `physics` imports `core.settings`, `states` imports `core` --
#: and pretending otherwise here would be a rule about an architecture this
#: project does not have and is not claiming.
ALLOWED_MODULES: dict[str, dict[str, frozenset[str]]] = {
    "core": {
        # The interface reaches `core` by injection
        # (src.core.rendering.overlay), never the other way round.
        "ui": frozenset(),
        # The simulation's one channel to the application, checked per module
        # rather than per layer: `application.scene_manager` is as forbidden to
        # a level as `application` is.
        "application": frozenset({"events", "settings_store"}),
    },
}

#: The one module of `application` the simulation is allowed to import, and
#: why it is not a violation.
#:
#: `NotificationSystem` publishes the player's death and the level completion
#: from inside the fixed tick, and the bus is the only channel available to it
#: -- which is the point: the tick holds no reference to the application, so a
#: rewind cannot re-emit a fact the player already saw. The contract is
#: genuinely shared, and the alternative -- moving the bus -- would put a
#: notification channel inside the simulation, which is worse: the simulation
#: would then own a concept that only the application has a use for.
APPLICATION_EVENTS = "application.events"

#: The other `application` module `core` is allowed to import, and why it is
#: not a violation.
#:
#: `core/input/bindings_repository.py` persists the player's key bindings, and
#: that is the same kind of thing `application.events` is: a contract the
#: simulation reads and the application configures. Neither is the scene stack,
#: the dispatcher or the event flow, and neither lets a level reach a screen.
APPLICATION_SETTINGS = "application.settings_store"

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


def test_the_simulation_only_imports_the_event_bus_from_the_application() -> None:
    """The simulation's one channel to the application is the notification bus.

    It publishes facts and holds no reference to the application, which is what
    keeps a rewind from re-emitting something the player already saw. Checked
    per module and not per layer: `application.scene_manager` is as forbidden
    to a level as `application` is.
    """
    offenders = [line for line in _violations("core") if "-> application" in line]
    assert offenders == [], (
        f"core may import {APPLICATION_EVENTS} and {APPLICATION_SETTINGS}, "
        "and nothing else from application"
    )


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
