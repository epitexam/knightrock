"""Repository-wide source conventions that no single module can enforce.

These are the checks that have to look at the whole tree: a rule that only
holds "somewhere in the codebase" cannot be asserted from inside the module
that follows it, because the interesting case is the module that does not.
"""

import io
import tokenize
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ExceptHeader:
    """The significant tokens of one `except` header, in source order."""

    tokens: tuple[tokenize.TokenInfo, ...]

    @property
    def line(self) -> int:
        return self.tokens[0].start[0]

    @property
    def text(self) -> str:
        return self.tokens[0].line.strip()

    @property
    def catches_several(self) -> bool:
        """True when the handler names more than one exception type."""
        names = sum(token.type == tokenize.NAME for token in self.tokens)
        operators = {
            token.string
            for token in self.tokens
            if token.type == tokenize.OP and token.string != "*"
        }
        return names > 1 or ("," in operators)

    @property
    def binds_a_name(self) -> bool:
        """True when the handler captures the exception (`except ... as e`)."""
        return any(token.type == tokenize.NAME and token.string == "as" for token in self.tokens)

    @property
    def parenthesized(self) -> bool:
        """True when the exception types are wrapped in brackets."""
        return any(token.type == tokenize.OP and token.string == "(" for token in self.tokens)


def _except_headers(source: str) -> list[ExceptHeader]:
    """Extract every `except` header from a source string.

    Tokenizing rather than parsing is required: on 3.14 `ast.parse` folds the
    bare `except A, B:` form into a `Tuple`, so the AST cannot tell the two
    spellings apart. The formatter, which does, rewrites one into the other.
    """
    headers: list[ExceptHeader] = []
    current: list[tokenize.TokenInfo] = []

    def flush() -> None:
        significant = [
            token
            for token in current
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
        if significant and significant[0].string in ("except", "except*"):
            headers.append(ExceptHeader(tuple(significant[1:])))
        current.clear()

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NEWLINE:
            flush()
            continue
        current.append(token)
    flush()
    return headers


def _misparenthesized_except_clauses() -> list[str]:
    """Report multi-exception handlers whose parentheses are redundant.

    PEP 758 (Python 3.14) makes the parentheses around the exception types
    optional, but only when the handler does not bind a name: `except A, B as
    e` is still a SyntaxError, so there the brackets are load-bearing. ruff
    enforces exactly this rule in the formatter. Asserting it here too keeps
    the two from drifting apart when someone runs the formatter on a subset of
    the tree, and it gives the rule a name instead of leaving it implicit.
    """
    offenders: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        for header in _except_headers(source):
            if not header.catches_several or header.binds_a_name or not header.parenthesized:
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{header.line}: {header.text}")
    return offenders


def test_redundant_except_parentheses_are_gone() -> None:
    """`except A, B:` without an `as` clause is the house style."""
    assert _misparenthesized_except_clauses() == []


def test_the_parens_detector_actually_detects() -> None:
    """Guard the guard: a detector that cannot fail proves nothing."""
    cases = {
        "try:\n    pass\nexcept (KeyError, ValueError):\n    pass\n": True,
        "try:\n    pass\nexcept KeyError, ValueError:\n    pass\n": False,
        "try:\n    pass\nexcept KeyError:\n    pass\n": False,
        "try:\n    pass\nexcept (KeyError, ValueError) as exc:\n    pass\n": False,
        "try:\n    pass\nexcept* KeyError, ValueError:\n    pass\n": False,
    }
    for source, expected in cases.items():
        assert bool(_misparenthesized_except_clauses_in(source)) is expected, source


def _misparenthesized_except_clauses_in(source: str) -> list[str]:
    """The single-source version of the check, for the self-test above."""
    return [
        header.text
        for header in _except_headers(source)
        if header.catches_several and not header.binds_a_name and header.parenthesized
    ]


def test_a_bare_multi_except_is_parsed_as_several_types() -> None:
    """The token view sees `except A, B:` as two types, parentheses or not."""
    for source in (
        "try:\n    pass\nexcept KeyError, ValueError:\n    pass\n",
        "try:\n    pass\nexcept (KeyError, ValueError):\n    pass\n",
    ):
        headers = _except_headers(source)
        assert len(headers) == 1, source
        assert headers[0].catches_several, source
        assert not headers[0].binds_a_name, source


@pytest.mark.parametrize("root", SOURCE_ROOTS)
def test_every_source_root_exists(root: str) -> None:
    """The file walk above is only meaningful while the roots are real."""
    assert (REPO_ROOT / root).is_dir()


def test_the_file_walk_actually_finds_the_package() -> None:
    """Guard the guard: an empty walk would make the check vacuously true."""
    found = _python_files()
    assert len(found) > 100
    assert REPO_ROOT / "src" / "core" / "game.py" in found
