# Knightrock

> A 2D hack 'n' slash platformer in Python with
> [pygame-ce](https://github.com/pygame-community/pygame-ce): frame-data combat,
> a deterministic fixed-timestep simulation, data-driven gameplay values and a
> built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.7%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-3864%20passing-brightgreen)](#quality)
[![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](#quality)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](#quality)

## Quick start

Requires **Python ≥ 3.14** and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
uv run python main.py            # play
uv run python main.py --debug    # play with the debug overlay
uv run python main.py --check    # boot and draw one frame, then exit
```

`--help` prints the usage. `--check` is the one-off command CI uses to verify a
build: it exits `0` when the frame draws and `1` with the full traceback on
stderr when it does not.

## Error reporting

A crash always writes the full traceback to stderr through `logger.critical`
and exits with code `1`. On a desktop the game also shows an interactive error
window (the whole traceback, a copy-to-clipboard button, and Quit / Back to main
menu); a crash before the display exists uses an asset-free window with the same
information. CI calls `--check` instead, so a headless run reports through
stderr and the exit code rather than waiting for input no driver can deliver.

## What it is

- **Frame-data combat**: high and low slashes and guards, chargeable attacks,
  beats, throws, death blows on a direction prompt, a slot machine and a fury
  gauge that opens the dark side.
- **Deterministic world**: a fixed 60 Hz simulation; collisions are sub-stepped,
  attack geometry is swept, and moving and one-way platforms use a spatial hash.
- **Data-driven values**: attacks, enemies, the player and the level registry live
  in tracked JSON under `data/gameplay/`.
- **Built for diagnosis**: an optional `DEBUG=1` test bench, overlay and a set of
  standalone benchmarks.

## Documentation

The details live in `docs/`, starting with the [documentation index](docs/README.md):

- [Controls and options](docs/controls.md)
- [Data-driven gameplay](docs/data.md)
- [Architecture and rendering](docs/architecture.md)
- [Debugging](docs/debugging.md) · [Benchmarks](docs/benchmarks.md)
- [Development and conventions](docs/development.md)
- [Tests and quality](docs/testing.md) · [Packaging](docs/packaging.md)
- [Audits and decisions](docs/audit/)

## Quality

3864 tests · 94 % instruction coverage · 84 % branch coverage · strict mypy
(212 files in `src`) · Ruff clean. These gates block CI; the commands and what
they protect are in [Tests and quality](docs/testing.md).
