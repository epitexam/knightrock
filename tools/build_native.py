"""Build the optional mypyc extensions for the hot physics helpers.

    uv run python tools/build_native.py            # compile into src/
    uv run python tools/build_native.py --verify   # check what Python imports
    uv run python tools/build_native.py --clean    # remove every built artifact

The source tree stays the source of truth: the ``.so`` files are generated,
ignored by git, and never required to run or test the game. Compilation happens
in a throwaway copy of ``src/`` because mypyc derives the extension's module
name from the path it is given; building ``src/physics/velocity.py`` from the
project root produces a module called ``physics.velocity`` instead of
``src.physics.velocity``, which fails to import. The finished extensions are
copied back to their real package paths with a manifest so ``--clean`` cannot
delete a file this script did not write.

The perimeter is deliberately narrower than ``src/physics/``:

- ``collisions``, ``movement`` and ``hit_resolver`` type an ECS ``SurfaceFlagsView``
  as ``dict[str, bool]``. Interpreted Python accepts the structural match; mypyc
  emits a real dict check and every contact raises ``TypeError``.
- ``contact_system`` calls the resolver above.
- ``entity_grid`` is subclassed by a test double. mypyc classes cannot be
  inherited by interpreted classes, so compiling it breaks the parity tests.

Everything in :data:`MODULES` compiles without changing a line of game code and
passes the full suite, the digests and the goldens in both modes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".native-manifest"

MODULES = (
    "src/physics/gravity.py",
    "src/physics/platforms.py",
    "src/physics/spatial_hash.py",
    "src/physics/spatial_query.py",
    "src/physics/velocity.py",
)


def _native_sources(source: Path) -> list[Path]:
    """The extensions mypyc actually produced, wherever it parked them."""
    libraries = sorted(source.glob("build/lib.*"))
    if not libraries:
        raise RuntimeError("mypyc produced no build directory")
    found = [path for library in libraries for path in library.rglob("*.so")]
    missing = [module for module in MODULES if not any(p.name.startswith(Path(module).stem + ".") for p in found)]
    if missing:
        raise RuntimeError(f"mypyc did not produce: {', '.join(missing)}")
    if not any("__mypyc." in path.name for path in found):
        raise RuntimeError("mypyc produced no shared runtime")
    return found


def build() -> list[Path]:
    """Compile the module list and install the extensions in the real tree."""
    with tempfile.TemporaryDirectory(prefix="knightrock-mypyc-") as scratch:
        temp = Path(scratch)
        shutil.copytree(ROOT / "src", temp / "src", ignore=shutil.ignore_patterns("*.so", "__pycache__"))
        shutil.copy(ROOT / "pyproject.toml", temp / "pyproject.toml")
        result = subprocess.run(
            [sys.executable, "-m", "mypyc", *MODULES],
            cwd=temp,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        # mypyc's final copy step insists on a `src/src/...` destination that
        # does not exist. The extensions themselves are in build/lib.* and are
        # valid; the check below is the one that matters, not that exit code.
        extensions = _native_sources(temp)

        installed: list[Path] = []
        for extension in extensions:
            relative = extension.relative_to(next(temp.glob("build/lib.*")))
            destination = ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(extension, destination)
            installed.append(destination)
        if result.returncode and not all(p.exists() for p in installed):
            raise RuntimeError(f"mypyc failed:\n{result.stdout[-4000:]}")
    MANIFEST.write_text("\n".join(str(p.relative_to(ROOT)) for p in installed) + "\n")
    return installed


def clean() -> None:
    """Remove the extensions for :data:`MODULES`, manifest or not.

    The manifest is the precise record when this script did the build. The
    fallback covers a build produced by hand (or by an older run that never
    wrote one), and is still scoped to the module list so no unrelated binary
    can be deleted.
    """
    paths: set[Path] = set()
    if MANIFEST.exists():
        paths = {ROOT / line for line in MANIFEST.read_text().splitlines() if line}
        MANIFEST.unlink()
    for module in MODULES:
        source = ROOT / module
        paths.update(source.parent.glob(f"{source.stem}.*.so"))
    paths.update(ROOT.glob("*_mypyc*.so"))
    for path in paths:
        if path.exists():
            path.unlink()


def verify() -> None:
    """Prove that Python picks the extensions, not the ``.py`` files."""
    import importlib

    # Running this file directly puts ``tools/`` on sys.path, not the project
    # root; import the same package path the game uses.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for module in MODULES:
        name = module.removesuffix(".py").replace("/", ".")
        imported = importlib.import_module(name)
        if not imported.__file__ or not imported.__file__.endswith(".so"):
            raise RuntimeError(f"{name} is still interpreted: {imported.__file__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--clean", action="store_true", help="remove the generated extensions")
    group.add_argument("--verify", action="store_true", help="check the modules Python imports")
    args = parser.parse_args()

    if args.clean:
        clean()
        print("native extensions removed")
    elif args.verify:
        verify()
        print(f"{len(MODULES)} modules are native")
    else:
        installed = build()
        print(f"built {len(installed)} extensions and {len(installed) - len(MODULES)} runtime(s)")


if __name__ == "__main__":
    main()
