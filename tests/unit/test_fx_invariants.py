"""The FX module's invariants, enforced.

The FX package documents its own rules in prose: a spawner checks the
budget, every particle declares a family, `__all__` is the surface, nothing
here touches simulation state. Prose is a claim. These are the checks that
notice the next convenient effect that skips one, and they are written the way
`test_layer_boundaries.py` writes its own -- against the tree with `ast`,
because the interesting case is the module that does not follow the rule,
not the one that does.

The checks that were real violations when the review found them started as
`xfail(strict=True)`, and each was removed by the commit that fixed it. Strict
was the part that mattered: when a fix made one pass, the marker turned into
an unexpected pass, the suite went red, and the marker had to go. A debt
marker that can be left behind is not a debt marker. There are none left.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FX_PACKAGE = REPO_ROOT / "src" / "core" / "fx"
FX_MODULE = FX_PACKAGE / "__init__.py"
SPAWNERS_MODULE = FX_PACKAGE / "spawners.py"
PARTICLES_MODULE = FX_PACKAGE / "particles.py"
DRAW_MODULE = FX_PACKAGE / "draw.py"
SETTINGS_MODULE = REPO_ROOT / "src" / "core" / "settings.py"
FX_TUNING_CLASSES = {"Dust", "Sweat", "FxGuard", "FxDizzy", "FxDecal"}
"""Where the FX tuning is declared. `Dust` and `Sweat` are here because they
predate the FX classes and the simulation reads a few of their numbers, so
they were extended rather than replaced."""
"""The three modules below the package root, in dependency order.

The rules are split along the same lines the package is: the budgets and the
particle classes live in one file each, so a check that says "the cap is
known to one place" and a check that says "every particle declares a family"
each have a single file to read.
"""
FX_MODULES = (DRAW_MODULE, PARTICLES_MODULE, SPAWNERS_MODULE, FX_MODULE)
SOURCE_ROOTS = ("src", "tests", "tools")


def _python_files() -> list[Path]:
    found: list[Path] = []
    for root in SOURCE_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" not in path.parts:
                found.append(path)
    return sorted(found)


def _tree(path: Path = FX_MODULE) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


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
    """The names a non-FX module reaches FX through, across the whole tree.

    Submodules are not part of this. `from src.core.fx import spawners` is a
    caller choosing a layer, which the split invited on purpose; it says
    nothing about whether the package root re-exports anything, and counting
    it would make the surface check pass on names nobody went through the
    root to get.
    """
    reached: set[str] = set()
    submodules = {path.stem for path in FX_MODULES}
    for path in _python_files():
        if FX_PACKAGE in path.parents:
            continue
        source = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(source):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if node.module.endswith("core.fx"):
                reached.update(alias.name for alias in node.names if alias.name not in submodules)
            elif node.module == "src.core":
                for alias in node.names:
                    if alias.name == "fx":
                        reached.update(
                            child.attr
                            for child in ast.walk(node)
                            if isinstance(child, ast.Attribute) and child.attr not in submodules
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
        spawner.name
        for spawner in _spawners(_tree(SPAWNERS_MODULE))
        if "_has_room" not in _called_names(spawner)
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
    assigned: set[str] = set()
    asked_for: set[str] = set()
    for node in ast.walk(_tree(PARTICLES_MODULE)):
        if isinstance(node, ast.Call):
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

    spawner_tree = _tree(SPAWNERS_MODULE)
    for node in ast.walk(spawner_tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_has_room"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            asked_for.add(node.args[1].value)

    budgets = next(
        node.value
        for node in spawner_tree.body
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
    assert asked_for, "no budget check found: the walk above is looking for the wrong shape"
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

    Two files in the package are exempt. ``spawners.py`` owns it, and the
    package root re-exports it, which is naming the cap rather than spending
    it. Everything else in `src` is scanned, including the rest of the
    package -- a cap checked in `particles.py` would be a second owner.
    """
    offenders: list[str] = []
    exempt = {"spawners.py", "__init__.py"}
    for path in (REPO_ROOT / "src").rglob("*.py"):
        in_package = FX_PACKAGE in path.parents
        if "__pycache__" in path.parts or (in_package and path.name in exempt):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "MAX_FX_SPRITES" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, f"the particle cap enforced outside the FX spawners: {offenders}"


# --- 4b. tuning lives in settings, not in the module -----------------------


def test_the_module_declares_no_tuning_of_its_own() -> None:
    """Sizes, speeds and lives belong to `settings`, so they can be read.

    `fx.py` used to hold its own thirty-odd constants and inline the rest.
    Both hide the same thing: a number you find by reading the function that
    uses it, named after that function, and which no one can look up when
    asking how fast the game feels. The budgets stay, because those are the
    module's contract with the plane and the check above reads them here.

    Reads the tree rather than the namespace so a tuning constant introduced
    as a float and a tuning constant introduced as an int are both caught.

    Private names are exempt, and only for the flag case: the frame cache
    keeps a `_frames_miss` sentinel, which is module state rather than
    something a reader would go looking for in a settings file.

    Scoped to module level, which is a deliberate limit rather than an
    oversight. A particle's `ClassVar` body is not scanned, so the rule is
    "no tuning constants at the top of the file" and not "no tuning numbers
    anywhere in it". The class bodies are covered from the other side by the
    check below, which fails when a setting is declared and nothing reads it.
    """
    allowed = {"MAX_FX_SPRITES", "FX_FAMILY_BUDGETS"}
    offenders: list[str] = []
    for node in _tree(PARTICLES_MODULE).body + _tree(SPAWNERS_MODULE).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id in allowed:
            continue
        if target.id.startswith("_"):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float)):
            offenders.append(target.id)
    assert not offenders, f"tuning declared in the FX package instead of settings: {offenders}"


def test_every_fx_setting_is_read_somewhere() -> None:
    """A setting nothing reads is worse than the literal it replaced.

    This is the hole the check above leaves, and it was left open by the
    commit that wrote it. Eighteen names were lifted out of `particles.py`
    into `settings.py` while the literals they named stayed where they were,
    so each of them had two places claiming to be the source and neither
    being it. Nothing failed, because nothing reads an unused name.

    It is also what catches the class bodies the module-level check cannot
    see: a proportion left inline in a particle is invisible there, and
    becomes visible here the moment someone declares it twice.

    Aliased imports are resolved, because the rest of the tree reads these
    classes as `GuardSettings` and `CombatSettings`; without that every one
    of them would look unread.
    """
    declared = _fx_setting_names()
    read = _settings_read_in_src()
    unread = sorted(
        f"{class_name}.{name}" for class_name, name in declared if (class_name, name) not in read
    )
    assert not unread, f"FX settings nothing reads: {unread}"


def _settings_read_in_src() -> set[tuple[str, str]]:
    """Every `Class.name` read on a settings class anywhere in `src`.

    Scoped to `src` and not the whole tree, so a setting that only a test
    reads does not count: the question is whether the game uses the knob, and
    a test asserting on a number is not the game using it.

    Not cached, on purpose. This is called once, from the one test that needs
    it, and it costs about half a second -- so there is no second call for a
    cache to serve. It was here while this function re-parsed the tree once
    per setting name, which is what took the file from two seconds to
    forty-five; the fix for that was to build the set in one pass, and the
    decorator was left behind. A cache here would also mean this function's
    answer could outlive the source it read, which for a check whose whole
    job is to report on the source is the wrong shape. Re-reading 0.4s of
    tree per run is the cheap option.
    """
    read: set[tuple[str, str]] = set()
    for path in (REPO_ROOT / "src").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = {
            alias.asname or alias.name: alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("settings")
            for alias in node.names
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                read.add((aliases.get(node.value.id, node.value.id), node.attr))
    return read


def _fx_setting_names() -> list[tuple[str, str]]:
    """The `(class, name)` pairs the six FX tuning classes declare."""
    tree = ast.parse(SETTINGS_MODULE.read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in FX_TUNING_CLASSES:
            for statement in node.body:
                if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                    continue
                target = statement.targets[0]
                if isinstance(target, ast.Name):
                    pairs.append((node.name, target.id))
    return pairs


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
