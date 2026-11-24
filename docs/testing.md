# Tests & quality

The suite is the contract: it runs headless, in a fixed order, and pins behaviour
rather than implementation. Start here before changing anything that touches
combat, rendering or settings.

```bash
uv run pytest
```

> **Current baseline:** 3841 tests · 94 % instruction coverage · 84 % branch
> coverage · Ruff clean · mypy clean (218 files across `src main.py tools`;
> `mypy src` alone is 212).[^coverage]

Tests run headless through the `SDL_*_DRIVER=dummy` variables, so they need no
display. Coverage, from:

```bash
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
uv run pytest --cov=src --cov-branch --cov-report=term-missing
```

Branch coverage is measured but **not gated**: CI compares the instruction
percentage against 80 % and nothing else. There is no `[tool.coverage]` section,
so `--cov-branch` is opt-in per command.

Static analysis — every check below is **blocking in CI**
(`.github/workflows/build.yml`):

```bash
uv run ruff check src tests main.py tools            # lint
uv run ruff format --check src tests main.py tools   # formatting
uv run mypy src main.py tools                         # types
```

`C901` has no standalone CI step — it is enforced because it sits in the ruff
`select` list consumed by the lint step. Ruff covers all four paths, 442 files.

`tests/` is **deliberately not type-checked**, which is why the mypy command omits
it.[^mypy-tests] The suite pins behaviour, not annotations, and test doubles are
intentionally loose; Ruff *does* cover `tests/`. Do not add `tests` to the mypy
command in `build.yml` without treating that debt first.

`pre-commit` runs the lint and format passes locally, auto-fixing rather than
checking, and does not run coverage:

```bash
uv run pre-commit install   # once
uv run pre-commit run --all-files
```

`tests/unit/test_readme_claims.py` runs as part of the suite and re-checks the
**root README**: it recounts the collected tests and asserts that every test-count
figure there equals the real one, and that the coverage badge and the coverage
pair agree with each other. It checks internal consistency, not truth — keep the
numbers in sync when they move.

## See also

- [Benchmarks](benchmarks.md) — measurement scripts are smoke-tested here, not timed.
- [Development](development.md) — conventions and the module reading map.

[^coverage]: Measured on this commit. `tests/unit/test_readme_claims.py` checks
    that the figures agree with each other, not that they agree with a run.

[^mypy-tests]: Adding `tests/` to the mypy gate means first paying roughly 1400
    errors across 122 files of intentionally loose test doubles. That figure grows
    with every new test module — re-measure with `uv run mypy tests` rather than
    trusting it, and note that it is far higher under recent mypy releases than
    when it was first recorded.
