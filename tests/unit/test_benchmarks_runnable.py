"""The benchmarks have to run.

`tests/benchmarks/*.py` hold no `test_` functions, so pytest collects nothing
from them and CI never executes a line. That is fine for a script and bad for a
file the README points at for frame timing: `ui_benchmark.py` sat broken for
several commits because it still read `renderer.ui_manager`, which stopped
existing when the core-to-ui dependency was inverted, and nothing noticed until
someone went looking for a number.

These are smoke tests, not measurements. They assert the entry point runs and
returns plausible keys; the timings they print are only meaningful from a real
run, and nothing here should ever be tuned to make one faster.
"""

import runpy
import sys
from pathlib import Path

import pytest

BENCHMARKS = Path(__file__).resolve().parent.parent / "benchmarks"


def _run(name: str, argv: list[str]) -> dict[str, float]:
    """Run a benchmark's ``main`` and capture what it put on stdout."""
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    saved = sys.argv
    sys.argv = [name, *argv]
    try:
        with redirect_stdout(buffer):
            runpy.run_path(str(BENCHMARKS / name), run_name="__main__")
    finally:
        sys.argv = saved
    return buffer.getvalue()


def test_contact_benchmark_runs() -> None:
    out = _run("contact_benchmark.py", ["--iterations", "2", "--repeats", "2"])
    assert out.strip(), "the contact benchmark printed nothing"


def test_render_benchmark_runs() -> None:
    out = _run("render_benchmark.py", ["--repeats", "2", "--window", "320", "240"])
    assert "ms" in out or "p50" in out


def test_ui_benchmark_runs() -> None:
    out = _run("ui_benchmark.py", ["--iterations", "2"])
    assert "cache_entries" in out, out[-400:]
    # A cache that never fills means the text cache stopped being consulted,
    # which no timing on this line would reveal.
    assert "cache_entries=0." not in out


@pytest.mark.parametrize("name", ["contact_benchmark.py", "render_benchmark.py", "ui_benchmark.py"])
def test_every_benchmark_is_reachable(name: str) -> None:
    """Each file is a script someone can actually invoke by path."""
    path = BENCHMARKS / name
    assert path.is_file(), f"{name} is listed in the README but does not exist"
    source = path.read_text()
    assert '__name__ == "__main__"' in source, f"{name} has no entry point"
