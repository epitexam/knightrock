# Knightrock

A 2D hack 'n' slash platformer in Python with [pygame-ce](https://github.com/pygame-community/pygame-ce): frame-data combat, a deterministic fixed-timestep simulation, data-driven gameplay values and a built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.7%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-3883%20passing-brightgreen)](#quality)
[![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](#quality)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](#quality)

## At a glance

| | |
|---|---|
| Genre | 2D hack 'n' slash platformer |
| Runtime | Python 3.14 and pygame-ce 2.5.7 or newer |
| Simulation | Fixed 60 Hz tick, swept collisions, spatial hash |
| Combat | Frame data, chargeable attacks, guards, death blows, throws, fury |
| Content | Tracked JSON under `data/gameplay/`; TMX levels and sprites in `assets/` |
| Tooling | uv, pytest, Ruff, strict mypy, PyInstaller |
| Diagnosis | `DEBUG=1` test bench, overlay and standalone benchmarks |

## Quick start

Requires Python 3.14 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --dev
uv run python main.py            # play
uv run python main.py --debug    # play with the debug overlay
uv run python main.py --check    # boot and draw one frame, then exit
```

`--help` prints the usage. `--check` is the one-off command CI uses to verify a build: it exits `0` when the frame draws and `1` with the full traceback on stderr when it does not.

## Error reporting

A crash always writes the full traceback to stderr through `logger.critical` and exits with code `1`. On a desktop the game also shows an interactive error window with the traceback, a copy-to-clipboard button, and Quit / Back to main menu; a crash before the display exists uses an asset-free window with the same information. CI calls `--check` instead, so a headless run reports through stderr and the exit code rather than waiting for input no driver can deliver.

## Documentation

This README is the front door. All detail lives in a self-contained documentation set under [`docs/`](docs/README.md).

| Area | Document | Covers |
|---|---|---|
| Product | [Features](docs/product/features.md) | Combat model and capabilities |
| Product | [Controls and options](docs/product/controls.md) | Bindings, moves, combat loop, settings screens |
| Product | [Gameplay data](docs/product/gameplay-data.md) | Tracked JSON, strict loading, fallback |
| Architecture | [Overview](docs/architecture/overview.md) | Fixed tick, scene stack, event bus |
| Architecture | [Rendering pipeline](docs/architecture/rendering.md) | Framing, window, camera, culling, draw planes |
| Architecture | [Combat and physics](docs/architecture/combat-and-physics.md) | Assists, knockback, ground pivot |
| Guides | [Development](docs/guides/development.md) | Module map and reading order |
| Guides | [Debugging](docs/guides/debugging.md) | `DEBUG=1` bench and overlay |
| Guides | [Benchmarks](docs/guides/benchmarks.md) | Standalone measurements |
| Guides | [Tests and quality](docs/guides/testing.md) | Gates and what they protect |
| Guides | [Packaging and releases](docs/guides/packaging.md) | PyInstaller spec and release flow |
| Reference | [Conventions](docs/reference/conventions.md) | Rules that are hard to see from one file |
| Reference | [Repository layout](docs/reference/repository-layout.md) | Annotated source tree |
| History | [Audits and decisions](docs/audit/README.md) | Audits, ADRs, playtests and design proposals |

## Quality

3883 tests · 94 % instruction coverage · 84 % branch coverage · strict mypy (212 files in `src`) · Ruff clean. These gates block CI; the commands and what they protect are in [Tests and quality](docs/guides/testing.md).
