# Documentation

[Back to README](../README.md)

This directory is a self-contained documentation set for Knightrock. The [root README](../README.md) is the front door: what the game is, how to launch it, and where the quality gates live. This index is the route into the detail.

## Start here

| Goal | Read |
|---|---|
| Play the game | [Quick start](../README.md#quick-start), [Controls](product/controls.md) |
| Tune the gameplay values | [Gameplay data](product/gameplay-data.md) |
| Understand a frame from input to screen | [Architecture overview](architecture/overview.md), [Rendering pipeline](architecture/rendering.md) |
| Understand combat and knockback | [Combat and physics](architecture/combat-and-physics.md) |
| Find a module or understand layer boundaries | [Repository layout](reference/repository-layout.md), [Conventions](reference/conventions.md) |
| Inspect the game live | [Debugging](guides/debugging.md), [Benchmarks](guides/benchmarks.md) |
| Run the gates before a change | [Tests and quality](guides/testing.md) |
| Build a release | [Packaging](guides/packaging.md) |
| Read past decisions and measurements | [Audits and historical decisions](audit/README.md) |

## Product

- [Features](product/features.md) - the combat model, capabilities and where things live.
- [Controls and options](product/controls.md) - keyboard, mouse and gamepad bindings, moves, the combat loop, and which screen owns each setting.
- [Gameplay data](product/gameplay-data.md) - the tracked JSON files, strict loading and the in-code fallback.

## Architecture

- [Overview](architecture/overview.md) - the fixed-tick simulation, scene stack and event bus.
- [Rendering pipeline](architecture/rendering.md) - framing, displays, window sizing, camera rounding, culling and draw planes.
- [Combat and physics](architecture/combat-and-physics.md) - assists, knockback, hit-stop and the ground pivot.
- [Repository layout](reference/repository-layout.md) - the annotated source tree.

## Guides

- [Development](guides/development.md) - module-by-module reading map and further notes.
- [Debugging](guides/debugging.md) - the `DEBUG=1` bench and overlay, and what each layer costs.
- [Benchmarks](guides/benchmarks.md) - standalone measurement scripts, including the optional mypyc A/B.
- [Tests and quality](guides/testing.md) - how to run the gates and what they protect.
- [Packaging and releases](guides/packaging.md) - the PyInstaller spec and the release flow.

## Reference

- [Conventions](reference/conventions.md) - typing, determinism, tuning and layout rules that are hard to see from one file.

## History and decisions

- [Audits and historical decisions](audit/README.md) - performance and refactor audits, ADRs, the Phase E plan, playtest notes and design proposals. These records are preserved as written.
