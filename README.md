# Knightrock

> A 2D hack 'n' slash platformer in Python with
> [pygame-ce](https://github.com/pygame-community/pygame-ce): frame-data combat,
> a deterministic fixed-timestep simulation, data-driven gameplay values and a
> built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.7%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-3841%20passing-brightgreen)](#quality)
[![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](#quality)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](#quality)

## Quick start

Requires **Python ≥ 3.14** and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
uv run python main.py            # play
uv run python main.py --debug    # play with the debug overlay
```

`--help` prints the usage.

## What it is

- **Frame-data combat**: high and low slashes and guards, chargeable attacks,
  beats, throws, death blows on a direction prompt, a slot machine and a fury
  gauge that opens the dark side.
- **Deterministic world**: a fixed 60 Hz simulation with swept collisions, moving
  and one-way platforms, and spatial hashing.
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

3841 tests · 94 % instruction coverage · 84 % branch coverage · strict mypy
(212 files in `src`) · Ruff clean. These gates block CI; the commands and what
they protect are in [Tests and quality](docs/testing.md).
