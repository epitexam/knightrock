"""The FX module's invariants, enforced.

`src/core/fx.py` documents its own rules in prose: a spawner checks the
budget, every particle declares a family, `__all__` is the surface, nothing
here touches simulation state. Prose is a claim. These are the checks that
notice the next convenient effect that skips one, and they are written the way
`test_layer_boundaries.py` writes its own -- against the tree with `ast`,
because the interesting case is the module that does not follow the rule,
not the one that does.

Five of the checks are `xfail(strict=True)`: each is a real violation the
architecture review found, and each is on a fix list. Strict is the part that
matters. When a fix makes one of them pass, the marker turns into an
unexpected pass, the suite goes red, and the marker has to be removed by the
commit that fixed it. A debt marker that can be left behind is not a debt
marker.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FX_MODULE = REPO_ROOT / "src" / "core" / "fx.py"
SOURCE_ROOTS = ("src", "tests", "tools")


def _python_files() -> list[Path]:
    found: list[Path] = []
    for root in SOURCE_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" not in path.parts:
                found.append(path)
    return sorted(found)


def _tree() -> ast.Module:
    return ast.parse(FX_MODULE.read_text(encoding="utf-8"))


def _names_in_dunder_all(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        ):
            return {
                element.value for element in node.value.elts if isinstance(element, ast.Constant)
            }
    raise AssertionError("fx.py has no __all__, so it has no declared surface")


def _fx_reexports() -> set[str]:
    """The names a non-FX module reaches FX through, across the whole tree."""
    reached: set[str] = set()
    for path in _python_files():
        if path == FX_MODULE:
            continue
        source = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(source):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module.endswith("core.fx"):
                reached.update(alias.name for alias in node.names)
            elif node.module == "src.core":
                for alias in node.names:
                    if alias.name == "fx":
                        reached.update(
                            child.attr
                            for child in ast.walk(node)
                            if isinstance(child, ast.Attribute)
                        )
    return reached


def _spawners(tree: ast.Module) -> list[ast.FunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("spawn_")
    ]


def _called_names(node: ast.AST) -> set[str]:
    return {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }


# --- 1. __all__ is the surface people actually use -------------------------


@pytest.mark.xfail(
    strict=True,
    reason="FxParticle, ImpactDecalParticle, facing_side and particle_frames are "
    "exported and reached by nobody. Cleared when the surface is reconciled.",
)
def test_every_exported_name_is_reached_from_outside_the_module() -> None:
    """A public name nothing reaches is a name nobody maintains.

    It looks like API, so the next person trusts it, and it survives every
    refactor because nothing breaks when it goes stale.
    """
    exported = _names_in_dunder_all(_tree())
    reached = _fx_reexports()

    orphans = exported - reached
    assert not orphans, f"exported but imported by nobody: {sorted(orphans)}"


# --- 2. and nothing outside is reached without being declared --------------


@pytest.mark.xfail(
    strict=True,
    reason="physics_system takes twelve undeclared tunables. Most move to "
    "settings.py when the tuning is gathered; the rest join __all__.",
)
def test_every_name_taken_from_fx_is_exported() -> None:
    """An import that works but is not in `__all__` is a name nobody can find.

    The other half of the previous check: a growing `__all__` alongside a
    growing set of undeclared imports is how a module's surface stops being a
    list anyone can rely on.
    """
    exported = _names_in_dunder_all(_tree())
    reached = _fx_reexports()

    undeclared = reached - exported
    assert not undeclared, f"imported from fx but absent from __all__: {sorted(undeclared)}"


# --- 3. every spawner respects the particle budget -------------------------


def test_every_spawner_checks_the_budget_before_adding() -> None:
    """The cap is the only thing standing between a burst and a frame spike.

    A spawner that trusts its caller has no cap of its own, so a second caller
    gets an uncapped one -- and the caller being in another module is exactly
    the coupling the cap exists to remove.
    """
    unchecked = [
        spawner.name for spawner in _spawners(_tree()) if "_has_room" not in _called_names(spawner)
    ]
    assert not unchecked, f"spawners that add particles with no budget check: {unchecked}"


# --- 4. every particle's family is budgeted --------------------------------


def test_every_family_is_budgeted() -> None:
    """A family the table does not know about is a family with no cap.

    The per-family budget only works if every family is in it, and the key is
    a string, so nothing but this check notices one that was missed. It reads
    both places a family can be named -- a particle's class body and a
    spawner's budget call -- because a spawner asking for a budget that does
    not exist is the same bug wearing a different hat.
    """
    tree = _tree()
    assigned: set[str] = set()
    asked_for: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "_has_room"
                and len(node.args) > 1
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                asked_for.add(node.args[1].value)
            continue
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        literal = node.value
        if not isinstance(literal, ast.Constant) or not isinstance(literal.value, str):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            named = (isinstance(target, ast.Attribute) and target.attr == "family") or (
                isinstance(target, ast.Name) and target.id == "family"
            )
            if named:
                assigned.add(literal.value)

    budgets = next(
        node.value
        for node in tree.body
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "FX_FAMILY_BUDGETS"
        )
        or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "FX_FAMILY_BUDGETS" for t in node.targets)
        )
    )
    known = {key.value for key in budgets.keys if isinstance(key, ast.Constant)}

    uncapped = (assigned | asked_for) - known
    assert assigned, "no family found: the walk above is looking for the wrong shape"
    assert not uncapped, f"families with no cap: {sorted(uncapped)}"

    unused = known - (assigned | asked_for)
    assert not unused, f"caps for families nothing spends from: {sorted(unused)}"


def test_the_particle_cap_is_known_to_one_place() -> None:
    """The cap is a property of the module that spends it.

    It was also enforced in `physics_system`, which meant two places to
    change when it moved and a spawner whose own check had been dropped still
    looked safe from the caller's side.

    Scoped to `src`: a test is supposed to read the cap, since filling a
    group to it is how the cap gets tested at all.
    """
    offenders: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        if path == FX_MODULE or "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "MAX_FX_SPRITES" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"the particle cap enforced outside fx.py: {offenders}"


# --- 5. the module never writes simulation state ---------------------------


def test_the_module_never_writes_an_entity_attribute() -> None:
    """FX is render-only, so the entity it is handed is a parameter, not a target.

    A write here would put cosmetic state on a thing the simulation snapshots,
    which is the one coupling this module is supposed to not have.
    """
    writers: list[str] = []
    for spawner in _spawners(_tree()):
        for node in ast.walk(spawner):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Store)
                and isinstance(node.value, ast.Name)
                and node.value.id in ("entity", "target")
            ):
                writers.append(f"{spawner.name}: {node.value.id}.{node.attr} = ...")
    for node in ast.walk(_tree()):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
        ):
            writers.append("setattr(...)")

    assert not writers, f"FX writing on an entity: {writers}"


# --- 6. and never reads the snapshotted RNG -------------------------------


def test_fx_does_not_draw_from_the_snapshotted_entity_rng() -> None:
    """``entity.rng`` state is captured by the rollback snapshot.

    So a render-only effect that draws from it advances state the simulation
    owns, and the stream position becomes a function of how much juice was on
    screen. It rewinds consistently today and nothing hashes it, so this is a
    latent trap rather than a live bug -- which is exactly why it wants a
    check instead of a comment.
    """
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "getattr" or not node.args:
            continue
        holder = node.args[0]
        literal = node.args[1] if len(node.args) > 1 else None
        if not isinstance(holder, ast.Name) or holder.id not in ("entity", "target"):
            continue
        if isinstance(literal, ast.Constant) and literal.value == "rng":
            pytest.fail(
                f"line {node.lineno}: FX reads {holder.id}.rng, whose state the "
                f"rollback snapshot captures"
            )


# --- 7. no noqa for a rule the project does not enable --------------------


@pytest.mark.xfail(
    strict=True,
    reason="two suppressions name PLC0415, and PL is not in ruff's select. A "
    "noqa for a rule that never runs reads as a reason and checks nothing.",
)
def test_no_suppression_for_a_rule_that_is_not_enabled() -> None:
    """A noqa for a rule that is not selected is a comment that looks like a guard.

    It survives the next person, who reads it as a reason not to move the
    import and then copies it for a rule that does run.
    """
    offenders: list[str] = []
    for path in _python_files():
        if path == Path(__file__):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "noqa: PLC0415" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"noqa for a rule the project does not enable: {offenders}"
