"""Repository-wide source conventions that no single module can enforce.

These are the checks that have to look at the whole tree: a rule that only
holds "somewhere in the codebase" cannot be asserted from inside the module
that follows it, because the interesting case is the module that does not.
"""

import io
import tokenize
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


def _bare_commas_in_except_line(tokens: list[tokenize.TokenInfo]) -> bool:
    """True when a logical line starting with `except` has a top-level comma.

    The comma that separates the exception types is only ambiguous when it
    sits outside brackets, so tracking bracket depth is enough to tell
    `except A, B:` from `except (A, B):`.
    """
    significant = [
        token
        for token in tokens
        if token.type
        not in (
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.NEWLINE,
            # Zero-width markers: a DEDENT is emitted on the same logical
            # line as the `except` that dedents to, and would hide it.
            tokenize.INDENT,
            tokenize.DEDENT,
        )
    ]
    if not significant or significant[0].string not in ("except", "except*"):
        return False
    depth = 0
    for token in significant[1:]:
        if token.type == tokenize.OP:
            if token.string in "([{":
                depth += 1
            elif token.string in ")]}":
                depth -= 1
            elif token.string == "," and depth == 0:
                return True
            elif token.string == ":" and depth == 0:
                return False
    return False


def _unparenthesized_except_clauses() -> list[str]:
    """Report `except A, B:` clauses, which only parse on Python 3.14+.

    PEP 758 allows the bare form and `ast.parse` quietly normalises it into a
    `Tuple`, so the AST cannot tell the two spellings apart. Both ruff and
    mypy target 3.14 as well, so neither of them will complain either.

    The rest of the codebase writes `except (A, B):`. A lone bare clause is a
    portability landmine that a backport, an automatic `pyupgrade`, or a
    contributor on an earlier interpreter would turn into a SyntaxError.
    """
    offenders: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        readline = io.StringIO(source).readline
        current: list[tokenize.TokenInfo] = []
        for token in tokenize.generate_tokens(readline):
            if token.type in (tokenize.NEWLINE,):
                if _bare_commas_in_except_line(current):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{token.start[0]}: {token.line.strip()}"
                    )
                current = []
                continue
            current.append(token)
    return offenders


def test_every_multi_exception_clause_is_parenthesized() -> None:
    """No `except A, B:` anywhere: the tuple form is the project convention."""
    assert _unparenthesized_except_clauses() == []


def test_the_unparenthesized_detector_actually_detects() -> None:
    """Guard the guard: a detector that cannot fail proves nothing."""
    for source, expected in (
        ("try:\n    pass\nexcept KeyError, ValueError:\n    pass\n", True),
        ("try:\n    pass\nexcept (KeyError, ValueError):\n    pass\n", False),
        ("try:\n    pass\nexcept KeyError:\n    pass\n", False),
        ("try:\n    pass\nexcept* KeyError, ValueError:\n    pass\n", True),
    ):
        lines: list[list[tokenize.TokenInfo]] = [[]]
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.NEWLINE:
                lines.append([])
                continue
            lines[-1].append(token)
        detected = any(_bare_commas_in_except_line(line) for line in lines)
        assert detected is expected, source


@pytest.mark.parametrize("root", SOURCE_ROOTS)
def test_every_source_root_exists(root: str) -> None:
    """The file walk above is only meaningful while the roots are real."""
    assert (REPO_ROOT / root).is_dir()


def test_the_file_walk_actually_finds_the_package() -> None:
    """Guard the guard: an empty walk would make the check vacuously true."""
    found = _python_files()
    assert len(found) > 100
    assert REPO_ROOT / "src" / "core" / "game.py" in found
