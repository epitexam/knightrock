# Knightrock

> A 2D hack 'n' slash platformer written in Python with
> [pygame-ce](https://github.com/pygame-community/pygame-ce) — frame-data combat,
> a deterministic fixed-timestep simulation, data-driven gameplay values and a
> built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-1117%20passing-brightgreen)](#tests--quality)
[![coverage](https://img.shields.io/badge/coverage-89%25-brightgreen)](#tests--quality)
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
- [Gameplay camera](#gameplay-camera)
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
| **Scene stack** | Menu, level select, options, controls, gameplay, pause, game-over and victory scenes with a synchronous, ordered [event bus](#architecture). |
| **Interface sounds** | One bus owns `pygame.mixer` and answers facts from the event bus (navigate, confirm, back); no screen names a cue or a file. Silent and non-fatal without a sound card, and the pointer speaks once per row it lands on. |
| **Debug test bench** | Hotkeys to spawn foes, fire pooled projectiles and force showcase attacks — no recompilation, no code edits. |
| **Quality gates** | 1117 tests, 89 % instruction / 86 % branch coverage, Ruff (lint, format, `C901`) and strict mypy (no per-module exemptions) — all blocking in CI. Ruff covers `src`, `tests`, `main.py` and `tools/`; mypy covers `src`, `main.py` and `tools/` ([`tests/` is deliberately not type-checked](#tests--quality)). |

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
| Dash | `Left Shift` (cancellable into an attack/guard) |
| Guard (tap = parry) | `Q` |
| Reset position | `R` |
| Attack 1 — light (aerial in the air) | `A` |
| Attack 2 — heavy (hold to charge, release to swing) | `S` |
| Attack 3 — uppercut | `D` |
| Attack 4 — dash attack (lunge; cancels a dash) | `F` |
| Special attack | `G` + `H` |
| Pause / resume | `Esc` / `Enter` |
| Menu navigation | `Enter` / `N` |
| Back in menus | `Esc` / right click |

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
| Menu navigation / confirm | Left stick or D-pad / `0` (`A`) |
| Back in menus | `1` (`B`) |

**In-game screens:** the main menu and the pause screen open **Options**, which
is a navigation hub — every setting lives in the screen that owns it:

- **Video settings** — display mode, window size, render scale, smooth scaling,
  VSync, frame limit, UI scale. Every row reports its value in its own column,
  and `←`/`→` set it. The **Window size** row opens a dedicated picker that
  draws in the same panel as the controls screen — title, a `STATE` column, a
  focus strip and a hint line — listing at once the sizes this screen can
  actually show, with the one in use marked `current` and the automatic choice
  marked `auto`. It is disabled in borderless, where a window size is
  meaningless.
- **Controls** → *Menu controls* (key/button rebinding and the menu stick Y
  inversion) and *Gameplay controls* (key/button rebinding).

Choices are written to `~/.knightrock/settings.json` and apply without
restarting. Each sub-menu has its own **Reset** that restores exactly what it
owns.

**The window adapts to the machine, and the game does not adapt to the window.**
These are two separate problems and the menu keeps them apart:

- the **display mode** and the **window size** default to *auto*: re-evaluated
  on every launch, so docking a laptop or running the game on another machine
  changes the answer. Borderless when the screen already has the shape of the
  framing, a window otherwise. A hand-picked size is honoured, and refused with
  a log line when the current screen can no longer show it;
- the sizes on offer are **fractions of the player's own screen** (40% to 95%),
  filtered by whether the result fits with room for a title bar. The old fixed
  list of absolute resolutions offered 2560x1440 to a 1366x768 laptop.

The window is resizable, and resizing it changes nothing about the game: the
visible world is a fixed rectangle in world units (see below), and the finished
frame is scaled to fit the window with the aspect preserved, the leftover
filled with black bars. The **Render scale** and **Smooth scaling** rows are
sharpness settings, and they are the ones to reach for when a large window makes
a frame expensive — measured, smooth scaling plus a 2x draw is 105% of a 60Hz
frame at 3840x2160.

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
  `F5` panels · `F6` freeze the simulation (debug only). `F7` steps one tick,
  `F8` replays an attack and `F9` exports it. Multi-box indices are drawn as
  in-situ vector points: the first is filled and the following ones hollow.
  Melee, projectile AABB and moving-hazard geometry use swept collision;
  static hazards and contact damage retain discrete collision. The full list
  is recalled on-screen by the `DEBUG KEYS` panel. `F4` statics is **off by
  default**: a level carries ~970 terrain tiles whose outline tells you
  nothing, and they were the largest single item in the frame at 2.8 ms.
  Measured on level 0 (972 sprites) with `DEBUG=1`, dropping the layer took
  the whole overlay pass from p50 6.0 ms to 4.3 ms.

## Framing: how much of the world is visible

The camera follows the player and shows a **fixed rectangle of the world**:
1152x648 world units, in `src/core/display/framing.py`. That number is the
whole framing policy. It is deliberately tight — the player sees 45% of the
width and 34% of the height of the shipped level — so the level has to be read
as it is entered rather than mapped from the menu, and tension comes from not
being able to see what is coming.

It used to be a **window** measurement. The camera was built from the window's
pixel size and a zoom constant, which made the visible world a free variable of
a video setting: the reveal ran from 34% of the level's height at the smallest
preset to 60% at the largest, and on the 40x15 levels a high enough preset
revealed a whole level, height included. A player could see more of a level by
opening the video menu. `test_framing_contract.py` now asserts the framing is
smaller than every `.tmx` in the level folder, and
`test_sim_is_display_independent.py` runs one input log at five window sizes
and three render scales and compares a world checksum.

How large the world is *drawn* is a separate question, answered by the render
scale: the art is authored at one pixel per world unit and the finished frame is
scaled to the window on its way out. So the camera has no zoom at all.

| Object | What it is |
|---|---|
| `Framing` | the visible rectangle of the world, in world units. Fixed. |
| `Viewport` | the fixed-size surface everything is drawn into |
| `Stage` | the OS window: mode, size, position, DPI, vsync |
| `Presentation` | viewport onto window, and the pointer back |

The invariant the four rest on: **the simulation reads `Framing` and nothing
else.** Window size, DPI, display mode and desktop dimensions are not
observable from it.

What follows from that:

- `Camera.apply()` is a pure translation, `screen = world - offset`. Sprites,
  health bars, hitboxes, labels and the debug overlays all read the one
  transform, so none of them can drift from the others;
- `Camera.apply_covering()` is what the renderer blits with. `apply()` returns
  exact fractional bounds and `pygame.Rect` truncates them, which always rounds
  a rectangle *in*: a tile at the far edge came out a pixel short, and the last
  column and row of the frame were painted by nothing and kept the background
  fill. It floors the near edges and ceils the far ones, so a rect covers its
  true extent. Fuzzing every framing, world size, camera offset and rect finds
  0 violations of that containment invariant;
- `Camera.is_visible()` culls against the framing rect;
- every frame is a complete repaint of the target, so a stale pixel is not
  possible rather than merely unlikely. That is what the fixed target bought:
  the incremental path, the dirty-rect budget and the overlay-rect bookkeeping
  are gone rather than merely tuned;
- a window resize reaches nothing that is drawn. `VIDEORESIZE` recomputes the
  letterbox rectangle and stops;
- the framing is **render-only**: sprite sizes, hitboxes, physics and the
  deterministic simulation are untouched, so goldens stay valid.

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
| `KNIGHTROCK_EXPORT_DIR` | Destination for F9 attack exports (default `~/.knightrock/exports/`). |
| `KNIGHTROCK_SAVE_DIR` | Override the save directory (default `~/.knightrock/`). |
| `SDL_VIDEODRIVER=dummy` | Headless rendering (CI, automated tests). |
| `SDL_AUDIODRIVER=dummy` | Headless audio (CI, automated tests). |

## Tests & quality

Run the suite:

```bash
uv run pytest
```

Coverage — CI enforces an 80 % instruction threshold (currently **89 %**):

```bash
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

Branch coverage is measured separately (currently **86 %**) and is *not*
compared against the instruction percentage:

```bash
uv run pytest --cov=src --cov-branch --cov-report=term-missing
```

Static analysis — every check below is **blocking in CI**:

```bash
uv run ruff check src tests main.py tools            # lint
uv run ruff format --check src tests main.py tools   # formatting
uv run ruff check src tests --select C901            # complexity (threshold 10)
uv run mypy src main.py tools                         # types
```

`src` carries no mypy per-module override any more, and
`disallow_incomplete_defs` is on globally, so a partially annotated signature
is a CI failure rather than something mypy quietly accepts.

`tests/` is **deliberately not type-checked**, which is why the mypy command
above omits it: running `uv run mypy tests` on its own reports 773 errors in 78
files. That is not a broken gate — the suite pins behaviour, not annotations,
and test doubles are intentionally loose. Do not add `tests` to the mypy
command in `.github/workflows/build.yml` without treating that debt first.
Ruff *does* cover `tests/`, so it is linted and format-checked like everything
else.

The same gates run
locally through `pre-commit`:

```bash
uv run pre-commit install   # once
uv run pre-commit run --all-files
```

> **Current baseline:** 1117 tests passing · 89 % instruction coverage ·
> 86 % branch coverage · Ruff clean · mypy clean (144 files across
> `src main.py tools`, the CI command; `mypy src` alone is 142). Tests run headless
> through the `SDL_*_DRIVER=dummy` variables, so
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
│   └── scenes/    menu · level select · options · controls · gameplay ·
│                  pause · game over · victory
├── core/          Bootstrap (game.py), settings, paths, colors, fx
│   ├── input/     Bindings, providers, managers, input state
│   ├── level/     Level facade + ordered fixed-tick systems
│   ├── rendering/ Camera (pure translation) and renderer
│   ├── display/   Framing, Viewport, Stage, Presentation, setup detection
│   ├── rollback/  Snapshot ring buffer and deterministic restore
│                   Asset library and animator (`core/asset_library.py`)
│                   Audio bus (`core/audio.py`)
├── combat/        Frame data, hit resolver, knockback, charge and combo
│                  tracking (CombatSystem lives in core/level/systems/)
├── entities/      Entity base, player + controllers, projectiles, vitals
│   └── enemies/   Data-driven configs, factory, per-type behaviour
├── physics/       Collisions, gravity, movement, spatial hash, entity grid
├── states/        State machines (player, enemies, shared reactions)
├── ui/            Player HUD, panels, world-space debug overlay
└── data/          Strict JSON loaders + in-code fallback values
data/gameplay/     Tracked JSON gameplay values (attacks, enemies, player, levels)
assets/            TMX levels and sprites — required at runtime (git-ignored)
notes/             Refactoring plans, audit reports and open gaps
```

**Reading the code, module by module**

- `src/core/game.py` owns the display, input and the scene stack; the loop feeds
  fixed ticks to the active scene, draws into the render target and presents
  it once. The loop is paced **exactly once**: with vsync off the `Clock` holds
  the frame limit, with vsync on the present already blocks on the vertical
  blank, so the clock is ticked only against a runaway ceiling derived from that
  rate — targeting 60 on top of a 60Hz present waits twice for one refresh and
  the cadence alternates between on time and one refresh late. The ceiling is a
  backstop, not a frame rate control, and it is derived rather than hardcoded so
  raising the limit can never leave it underneath. A frame runs at most
  `Simulation.MAX_TICKS_PER_FRAME` ticks and the surplus is dropped: the
  accumulator's own clamp bounds a single frame, and only accumulated debt from
  a sustained overload can exceed that.
- `src/core/level/systems/gameplay_loop.py` defines the *order* in which the
  level systems run; each system stays independently testable.
- `src/application/events.py` is a synchronous, strictly ordered event bus with
  two families of facts: simulation milestones (`LevelStarted`, `PlayerDied`,
  `LevelCompleted`, emitted from the fixed tick by a `Level` that holds no
  reference to the application) and interface feedback (`UiFeedback`, emitted by
  the input dispatcher from what a screen reports). Subscribers (UI, save, audio,
  logs) must never mutate the simulation.
- `src/core/audio.py` is the only module that touches `pygame.mixer`, and it is a
  **consumer**: it never asks who did something and imports neither the input
  router, the menu model, the scenes nor the views. `cue_for(effect)` is the whole
  policy — one effect, one cue — and `attach(bus)` subscribes to the facts it
  answers, so a single line in the application layer knows the audio system
  exists. It loads each sound once, caches it, applies the volume of the cue's
  category and never raises: no sound card, no asset and an undecodable file all
  end with a warning and a silent cue, which is also the CI path since `assets/`
  is git-ignored. Silence is structural rather than a setting: a screen reports
  `None` when it did nothing, so the gameplay keys the player holds and a key
  swallowed by a rebinding capture are never announced.
- Combat is frame-data driven: startup / active / recovery phases feed
  `HitboxManager` and `HitResolver` through the two-pass deterministic
  `CombatSystem`.

## Conventions

- **Typed code.** `mypy src main.py tools` is blocking
  (`disallow_untyped_defs = true`, `disallow_incomplete_defs = true`) with
  **no per-module override left** in
  `pyproject.toml`, so a partially annotated signature is a CI failure rather
  than something mypy quietly accepts. `tests/` is excluded, on purpose.
- **Formatted & measured.** `ruff format` for style, `ruff --select C901` for
  cyclomatic complexity (threshold 10, every exception justified).
- **Deterministic simulation.** Fixed timestep (`Simulation.TICK_RATE = 60`);
  rendering follows `Display.FPS`. Nothing may introduce non-determinism into
  the tick.
- **Centralized tuning.** Gameplay constants live in `src/core/settings.py` —
  no magic numbers in the systems. A constant **shared by two modules has
  exactly one home**, and it belongs to the module that acts on it: the HP bar
  geometry is defined once in `src/ui/world_ui.py`, which draws it, and
  `src/core/rendering/renderer.py` imports it rather than redefining it. Two
  copies agree only until someone edits one. UI-only constants
  (`HUD_PIP_SIZE`, `HEALTH_BAR_*`) stay in their UI module, and renderer
  internals (`DASH_STRETCH_*`) stay next to their only user.
- **No dead menu options.** User-facing hotkeys are mirrored by tests
  (`DEBUG KEYS` panel, bindings, attack sets).

## Documentation

- `notes/audit_consolide.md` — consolidated code audit (written in French).
- `notes/audit_ui.md` and `notes/audit_controles.md` — UI and input audits, with
  the delivery matrix and acceptance checklist (written in French).
- `notes/ecarts_ouverts.md` — open gaps and the measured reference baseline
  (written in French).
- `notes/hitbox_amelioration.md` — hitbox and advanced-combat work, with
  `notes/plan_hitbox_amelioration_partiels.md` for the partial-compliance
  follow-up (written in French).
- `notes/plan_limit_frames_video.md` — planned frame-limit setting for the
  video menu, with the measurements that bound it (written in French).
