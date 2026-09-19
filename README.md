# Knightrock

> A 2D hack 'n' slash platformer written in Python with
> [pygame-ce](https://github.com/pygame-community/pygame-ce) — frame-data combat,
> a deterministic fixed-timestep simulation, data-driven gameplay values and a
> built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-665%20passing-brightgreen)](#tests--quality)
[![coverage](https://img.shields.io/badge/coverage-91%25-brightgreen)](#tests--quality)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](#tests--quality)

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running the game](#running-the-game)
- [Controls](#controls)
- [Phase 5 test bench](#phase-5-test-bench-hitbox--advanced-combat)
- [Debug overlay](#debug-overlay-debug1)
- [Physics engine](#physics-engine-assists-on-by-default)
- [Knockback & hit feedback](#knockback--hit-feedback)
- [Data-driven gameplay](#data-driven-gameplay)
- [Tests & quality](#tests--quality)
- [Packaging & releases](#packaging--releases)
- [Architecture](#architecture)
- [Conventions](#conventions)
- [Documentation](#documentation)

---

## Features

| Capability | What it does |
|---|---|
| **Frame-data combat** | Startup / active / recovery phases, chargeable heavies, combos, juggles, OTG guard and multi-hitbox attacks. |
| **Deterministic physics** | Fixed 60 Hz simulation, sub-stepped swept collisions, moving platforms, one-way platforms and spatial hashing. |
| **Data-driven design** | Attacks, enemies, the player and the level registry live in tracked JSON, validated with strict errors and safe fallbacks. |
| **Scene stack** | Menu, gameplay, pause and game-over scenes with a synchronous, ordered [event bus](#architecture). |
| **Debug test bench** | Hotkeys to spawn foes, fire pooled projectiles and force showcase attacks — no recompilation, no code edits. |
| **Quality gates** | 665 tests, 91 % instruction / 88 % branch coverage, Ruff (lint, format, `C901`) and strict mypy — all blocking in CI. |

---

## Requirements

- **Python ≥ 3.14** (see `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — dependency and virtualenv manager

## Installation

```bash
uv sync --dev
```

`--dev` also installs the test and quality tooling (`pytest`, `pytest-cov`,
`ruff`, `mypy`). Drop it for a runtime-only environment.

## Running the game

```bash
uv run python main.py
```

With the debug overlay (FPS, states, hitboxes, panels):

```bash
DEBUG=1 uv run python main.py
```

## Controls

**Keyboard**

| Action | Key |
|---|---|
| Move | `Left arrow` / `Right arrow` |
| Fast fall | `Down arrow` |
| Jump | `Space` |
| Dash | `Left Shift` |
| Guard (tap = parry) | `Q` |
| Reset position | `R` |
| Attack 1 — light (aerial in the air) | `A` |
| Attack 2 — heavy (hold to charge, release to swing) | `S` |
| Attack 3 — uppercut | `D` |
| Attack 4 — dash attack | `F` |
| Special attack | `G` + `H` |
| Pause / resume | `Esc` / `Enter` |
| Menu navigation | `Enter` / `N` / `Esc` |

**Gamepad**

| Action | Button / axis |
|---|---|
| Move | Left stick (axis 0) |
| Jump | `0` |
| Attack 1 | `1` |
| Attack 2 | `2` |
| Attack 3 | `3` |
| Guard (tap = parry) | `4` |
| Attack 4 | `5` |
| Reset | `7` |
| Dash | Axis `2` |
| Special attack | `1` + `3` |

**Debug spawns:** `G` goblin · `P` slime · `T` dummy.

## Phase 5 test bench (hitbox / advanced combat)

Every showcase feature is reachable from a single hotkey, live in game — nothing
to recompile, no code to edit:

| Key | Feature under test | Detail |
|:---:|---|---|
| `1` | Multi-hitbox (#1) | `twin_fangs` — blade plus a second, disjoint box |
| `2` | Animated hitbox (#2) | `sweeping_arc` — the box grows along its keyframe curve |
| `3` | Juggle (#4) | `sky_launcher` — launches upward with softened gravity (`×0.5`) |
| `4` | OTG (#4) | `otg_slam` — the only attack allowed during the OTG guard |
| `V` | Projectile (#3) | plain `firebolt`, reuses `HitResolver` |
| `B` | Piercing projectile (#3) | passes through and hits each target once |
| `C` | Juggle dummy | pops an airborne dummy in front of the player |

**Suggested protocol:** press `C`, then `3` under the dummy (neutral while
airborne) to start the juggle; juggle mid-air with `A` during the jump, then
finish on the ground with `4` while the OTG guard is active. The debug overlay
(`DEBUG=1`) shows the offensive boxes, `Combo (air xN)`, `Juggle`, `OTG guard`
and the `Shots` counter in the SCENE panel.

## Debug overlay (`DEBUG=1`)

The overlay only draws what is on screen (viewport culling), which keeps the
frame cost predictable:

- **Hitboxes** — blue = player, red = enemy, grey = neutral. Overlaid with the
  green hurtbox, the orange offensive box and the velocity arrow: **red**
  while the hit that caused it is fresh or while the knockback state still
  carries the entity, **gold** on a parry, yellow for locomotion.
- **Velocity arrows** — a tapered shaft, a filled triangular head and a pivot
  dot on the entity, all wrapped in a dark rim so the silhouette survives a
  bright sky. The head length is clamped and short vectors are stretched to a
  minimum drawn length, so a slow walk and a dash both stay legible.
- **Outlines** — cyan = OTG guard, purple = juggle gravity.
- **Labels** — short cards (`Goblin chase 75/100`); a second line appears only
  during an attack or when a flag is set (`STAG`, `OTG`, `JGx`, `AIR`).
  Projectiles are labelled with speed, lifetime and pierce; tiles are skipped
  and static props render without text.
- **Toggles** — `F1` boxes · `F2` labels · `F3` velocities · `F4` statics ·
  `F5` panels · `F6` freeze the simulation (debug only). The full list is
  recalled on-screen by the `DEBUG KEYS` panel.

## Physics engine (assists on by default)

All knobs live in `src/core/settings.py` under `GameFeel`, `Collision` and
`PlatformRide`. Set a value to `0` (or `1` for the jump cut) to restore the
legacy, assist-free behaviour:

| Constant | Effect |
|---|---|
| `JUMP_CUT_DIVISOR` | Variable jump height — releasing the button cuts the rise. |
| `GROUND_SNAP_PX` | Sticks to the ground instead of floating off platform edges. |
| `STEP_UP_PX` / `CORNER_CORRECT_PX` | Auto-mounts small steps, nudges around ceiling corners. |
| `MIN_PENETRATION_PX` | Grazes keep sliding instead of stopping dead. |
| `MAX_RESOLVE_PX` | Anti-teleport guard; deeper overlaps flag the entity as `crushed`. |
| `STICKY_FACTOR` | Stay mounted on fast-descending platforms. |
| `APEX_GRAVITY_DIVISOR` | Reduced gravity at the jump apex for a longer hang time. |
| `FAST_FALL_GRAVITY_MULTIPLIER` | Extra fall acceleration while the down key is held. |

## Knockback & hit feedback

Tuned through `Combat` and `CameraShake` in `src/core/settings.py`:

- `WALL_BOUNCE_FACTOR` — mid-launch entities rebound off walls (red arrow in
  debug) instead of stopping dead.
- `KNOCKBACK_MAX_DURATION` — anti-lock safety for pits; `KNOCKBACK_DI_ACCEL` /
  `KNOCKBACK_DI_CAP` — the player can steer an airborne trajectory, enemies
  cannot.
- `JUGGLE_DECAY_STEP` / `JUGGLE_DAMAGE_FLOOR` — diminishing returns on
  consecutive juggle hits.
- `HITSTOP_KNOCKBACK_FACTOR` and `CameraShake` — hit-stop and screen shake
  scaled to impact magnitude (launches ≥ 400 trigger trauma).

## Data-driven gameplay

Attacks, enemies, the player and the level registry live in **tracked JSON**
under `data/gameplay/`. These files are versioned (unlike `assets/`), so balance
changes are reviewable in a pull request. The frozen dataclasses stay the
runtime model.

| File | Contents |
|---|---|
| `attacks.json` | Named attack sets (`player`, `goblin`, `slime`, …) with full frame data. |
| `enemies.json` | Enemy configs, referencing attack sets by name or inlining them. |
| `player.json` | Player overrides plus the attack-name list. |
| `levels.json` | Level id to TMX path mapping. |

Loading is **strict**: unknown keys, missing fields, bad versions and unknown
attack references raise `GameplayDataError`. A *missing* file falls back to the
historical in-code values with a warning, so the game never refuses to boot over
a data problem.

**Environment variables**

| Variable | Purpose |
|---|---|
| `DEBUG=1` | Enable the debug overlay and hotkeys. |
| `KNIGHTROCK_DATA_DIR` | Alternate root containing `gameplay/*.json` (modders, tests). |
| `KNIGHTROCK_SAVE_DIR` | Override the save directory (default `~/.knightrock/`). |
| `SDL_VIDEODRIVER=dummy` | Headless rendering (CI, automated tests). |
| `SDL_AUDIODRIVER=dummy` | Headless audio (CI, automated tests). |

## Tests & quality

Run the suite:

```bash
uv run pytest
```

Coverage — CI enforces an 80 % instruction threshold (currently **91 %**):

```bash
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

Branch coverage is measured separately (currently **88 %**) and is *not*
compared against the instruction percentage:

```bash
uv run pytest --cov=src --cov-branch --cov-report=term-missing
```

Static analysis — every check below is **blocking in CI**:

```bash
uv run ruff check src tests                 # lint
uv run ruff format --check src tests        # formatting
uv run ruff check src tests --select C901   # cyclomatic complexity (threshold 10)
uv run mypy src                             # types
```

> **Current baseline:** 665 tests passing · 91 % instruction coverage ·
> 88 % branch coverage · Ruff clean (197 files formatted) · mypy clean on
> 120 files. Tests run headless through the `SDL_*_DRIVER=dummy` variables, so
> they need no display.

## Packaging & releases

The game ships as a standalone PyInstaller bundle driven by `knightrock.spec`
(it embeds `assets/` and `data/`):

```bash
uv run --with pyinstaller==6.22.2 pyinstaller knightrock.spec --noconfirm --clean
```

`.github/workflows/build.yml` then:

1. runs tests, lint, format and mypy on every push / pull request to `master`;
2. builds `knightrock-linux`, `knightrock-windows` and `knightrock-macos`
   artifacts, with a **headless smoke test** that boots the packaged binary;
3. publishes a GitHub Release with those artifacts when a `v*` tag is pushed.

## Architecture

```
src/
├── application/   Scene stack, event bus, save game
│   └── scenes/    menu · gameplay · pause · game over · menu panel
├── core/          Bootstrap (game.py), settings, paths, colors, fx
│   ├── input/     Bindings, providers, managers, input state
│   ├── level/     Level facade + ordered fixed-tick systems
│   ├── rendering/ Camera, renderer, dirty-rect presentation
│   ├── rollback/  Snapshot ring buffer and deterministic restore
│   └── animation/ Asset library and animator
├── combat/        Frame data, combat component/system, hit resolver,
│                  knockback, charge and combo tracking
├── entities/      Entity base, player + controllers, projectiles, vitals
│   └── enemies/   Data-driven configs, factory, per-type behaviour
├── physics/       Collisions, gravity, movement, spatial hash, entity grid
├── states/        State machines (player, enemies, shared reactions)
├── ui/            Player HUD, panels, world-space debug overlay
└── data/          Strict JSON loaders + in-code fallback values
data/gameplay/     Tracked JSON gameplay values (attacks, enemies, player, levels)
assets/            TMX levels and sprites — required at runtime (git-ignored)
docs/ · notes/     Refactoring plans and audit reports
```

**Reading the code, module by module**

- `src/core/game.py` owns the display, input and the scene stack; the loop only
  feeds fixed ticks to the active scene and presents its dirty rects.
- `src/core/level/systems/gameplay_loop.py` defines the *order* in which the
  level systems run; each system stays independently testable.
- `src/application/events.py` is a synchronous, strictly ordered event bus:
  subscribers (UI, save, audio, logs) must never mutate the simulation.
- Combat is frame-data driven: startup / active / recovery phases feed
  `HitboxManager` and `HitResolver` through the two-pass deterministic
  `CombatSystem`.

## Conventions

- **Typed code.** `mypy src` is blocking (`disallow_untyped_defs = true`) with
  narrow overrides for the few modules still being migrated; `src.combat`,
  `src.entities` and `src.states` have been strict-clean since RF-8.
- **Formatted & measured.** `ruff format` for style, `ruff --select C901` for
  cyclomatic complexity (threshold 10, every exception justified).
- **Deterministic simulation.** Fixed timestep (`Simulation.TICK_RATE = 60`);
  rendering follows `Display.FPS`. Nothing may introduce non-determinism into
  the tick.
- **Centralized tuning.** Gameplay constants live in `src/core/settings.py` —
  no magic numbers in the systems.
- **No dead menu options.** User-facing hotkeys are mirrored by tests
  (`DEBUG KEYS` panel, bindings, attack sets).

## Documentation

- `docs/plans/` — refactoring plans (knockback debug arrow, reaction authority).
- `notes/audit.md` and `notes/audit_phase5.md` — code audits (written in French).
- `notes/refactoring_handoff.md` — refactoring backlog and measured baselines
  (written in French).
