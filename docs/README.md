# Documentation

The [root README](../README.md) is a short introduction: what the game is, how to
start it, where the quality gates are. Everything below goes deeper.

## The project in detail

| Capability | What it does |
|---|---|
| **Hack 'n' slash combat** | No More Heroes 2 in 2D: high and low slashes against high and low guards, a blade battery to recharge by hand, beats that stun and throws, death blows on a direction prompt, a slot machine, blade locks, a dark step that slows the world and a fury gauge that opens the dark side -- on frame data with startup / active / recovery phases and multi-hitbox attacks. |
| **Deterministic physics** | Fixed 60 Hz simulation, sub-stepped swept collisions, moving platforms, one-way platforms, spatial hashing. |
| **Data-driven design** | Attacks, enemies, the player and the level registry live in tracked JSON, validated with strict errors; the attacks, enemies and player have no copy in code. |
| **Scene stack** | Menu, level select, options, video, controls, gameplay, pause, game-over and victory scenes over a synchronous, ordered [event bus](architecture.md#architecture). |
| **Interface sounds** | One bus owns `pygame.mixer` and answers facts from the event bus (navigate, confirm, back). No screen names a cue or a file. Silent and non-fatal without a sound card. |
| **Debug test bench** | Hotkeys to spawn foes, fire pooled projectiles and force showcase attacks — no recompilation, no code edits. |
| **Quality gates** | 3841 tests, strict mypy and Ruff (lint, format, `C901`), all blocking in CI. |

## Using and tuning the game

- [Controls and options](controls.md) — every keyboard, mouse and gamepad binding,
  the prompts, and the settings screens that own each choice.
- [Data-driven gameplay](data.md) — the tracked JSON files for attacks, enemies,
  the player and levels, and how they become runtime objects.
- [Debugging](debugging.md) — the `DEBUG=1` test bench and overlay, and what each
  diagnostic layer costs.
- [Benchmarks](benchmarks.md) — the commands for the dedicated benchmark scripts,
  including the optional mypyc A/B.

## Understanding the code

- [Architecture and rendering](architecture.md) — framing, camera rounding, culling,
  physics, combat, draw planes and the scene/event-bus architecture.
- [Development](development.md) — a module-by-module reading map, conventions and
  further notes.
- [Tests and quality](testing.md) — how to run the gates and what they protect.
- [Packaging and releases](packaging.md) — the PyInstaller spec and the release flow.

## Audits and decisions

- [audit/](audit/) — performance and refactor audits, including the Phase E plan
  and the measurements behind the optional optimizations.
- [Playtest notes](playtest-2026-11-18.md) — observations from the November 2026
  playtest.
- [Hitbox fluidity PR notes](pr-fix-hitbox-fluidity.md) — the reasoning behind the
  hitbox feel fix.
