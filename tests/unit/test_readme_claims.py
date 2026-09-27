"""The quality figures the README advertises must be the real ones.

A README that quotes a test count and a coverage percentage is a claim, and
a stale claim is worse than none: it is the number people trust when they
decide whether a change is safe. The audit found 1511 quoted against 1813
actual, so the numbers are now checked instead of remembered.

The test count is verified for real, because `pytest --collect-only` costs
well under a second. The coverage percentages are only checked for internal
consistency -- measuring them takes a full instrumented run -- and are
verified by hand against the command in the README's Tests & quality
section.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"


def _collected_test_count() -> int:
    """How many tests pytest collects, counted the same way CI would."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"(\d+) tests? collected", completed.stdout)
    assert match is not None, completed.stdout[-2000:]
    return int(match.group(1))


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_the_readme_quotes_the_test_count_that_exists() -> None:
    """Every "N tests" figure in the README equals what pytest collects."""
    actual = _collected_test_count()
    quoted = {int(value) for value in re.findall(r"(\d{3,5}) tests?\b", _readme_text())}

    assert quoted, "the README is expected to advertise a test count"
    assert quoted == {actual}, (
        f"README quotes {sorted(quoted)} tests but pytest collects {actual}. "
        "Update every occurrence, not just the first."
    )


def test_the_collection_guard_is_not_vacuous() -> None:
    """A count of zero would make the comparison above pass for free."""
    assert _collected_test_count() > 1000


def test_the_coverage_figures_agree_with_each_other() -> None:
    """Badge, summary table and baseline block must quote one coverage pair.

    Not verified against a real measurement here (that needs an instrumented
    full run); this only catches the common drift, where one of the three is
    updated and the other two are not.
    """
    readme = _readme_text()
    pairs = {
        (int(instruction), int(branch))
        for instruction, branch in re.findall(
            r"(\d+)\s*% instruction\D{0,20}?(\d+)\s*% branch", readme
        )
    }
    badge = re.search(r"badge/coverage-(\d+)%25", readme)

    assert badge is not None, "the coverage badge is expected to exist"
    assert len(pairs) == 1, f"the README quotes several coverage pairs: {sorted(pairs)}"
    instruction, branch = pairs.pop()
    assert instruction == int(badge.group(1)), (
        f"badge says {badge.group(1)} % instruction, the prose says {instruction} %"
    )
    assert 0 < branch <= instruction, "branch coverage cannot exceed statement coverage"
