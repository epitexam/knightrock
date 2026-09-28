# Knightrock

> A 2D hack 'n' slash platformer written in Python with
> [pygame-ce](https://github.com/pygame-community/pygame-ce) — frame-data combat,
> a deterministic fixed-timestep simulation, data-driven gameplay values and a
> built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-2100%20passing-brightgreen)](#tests--quality)
[![coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)](#tests--quality)
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
| **Quality gates** | 2100 tests, 93 % instruction / 85 % branch coverage, Ruff (lint, format, `C901`) and strict mypy (no per-module exemptions) — all blocking in CI. Ruff covers `src`, `tests`, `main.py` and `tools/`; mypy covers `src`, `main.py` and `tools/` ([`tests/` is deliberately not type-checked](#tests--quality)). |

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

A stick is a position, not a press, so the two say different things. A quarter of
its travel moves one row; **pushing further scrolls** and easing back stops it,
without stepping backwards. The D-pad has no partial travel to read, so holding
it scrolls on its own. Both the D-pad and the stick auto-repeat, the keyboard
included, and only the four directions repeat: a held confirm would open and
close a menu in a loop.

**In-game screens:** the main menu and the pause screen open **Options**, which
is a navigation hub — every setting lives in the screen that owns it:

- **Video settings** — display mode, whole-pixel art, VSync, frame limit, UI
  scale, and a read-out of what the game derived from the window. Every row
  reports its value in its own column, and `←`/`→` set it. There is no
  **resolution** row, and that is the point: a list of window sizes is a claim
  about the player's monitor that the game cannot check, and a remembered size
  is a claim that goes stale — in borderless the window is the screen's own size
  whatever the file says, so the row used to display a number the game was not
  using. The window belongs to the window manager now; the game resizes the
  picture when the player resizes the window.
- **Controls** → *Menu controls* (key/button rebinding and the menu stick Y
  inversion) and *Gameplay controls* (key/button rebinding). Each screen ends
  on a separated, greyed block of options — the Y inversion, **Reset to
  defaults** and **Back**. They are choices rather than slots, so they carry no
  key: a row that looks like the others and cannot take a binding is a row you
  press a key on and nothing happens.

Choices are written to `~/.knightrock/settings.json` and apply without
restarting. Each sub-menu has its own **Reset** that restores exactly what it
owns — the video one leaves your controls alone. A file that cannot be read is
reported in the log with the reason instead of being silently replaced by the
defaults, and the file being overwritten is kept as `settings.json.bak`.

**The window is the only source of truth about the window.** There is no stored
size, no `size_mode`, no render scale and no smoothing flag, and no video setting
can go stale because none of them describes a screen:

- the **display mode** defaults to *auto*: borderless when the screen already has
  the shape of the framing, a window otherwise, re-evaluated on every launch. A
  chosen mode is never re-resolved;
- a **windowed** game opens as large as fits with room for its own title bar, and
  that is all. Drag it to whatever you like;
- the **render target is the window** — more precisely, the rectangle of the
  window that carries the picture at the framing's aspect, the rest being bars.
  The finished frame is blitted **1:1**, so the picture is exactly the picture at
  any window size, and the measured cost of presenting it is a copy rather than a
  resample: ~0.4 ms at 1280×720, ~2.4 ms at 2560×1440, against 3.95 ms and 7.46 ms
  of `smoothscale` for the same windows;
- the **pixel density** — how many pixels a world unit gets — is read back off
  that rectangle, never chosen. It is a fraction on most displays (1.667 at
  1920×1080), and the art is magnified once per window, at load;
- **whole-pixel art** gives up filling the window to get every art pixel as an
  exact *k*×*k* block: the picture becomes the largest whole multiple of the
  framing that fits and the bars take the rest. It is a no-op on a window smaller
  than the framing, and the row says so.

Resizing the window rebuilds the render target, re-reads the density and re-lays
out the interface — the same cascade as a display change, which is why it is one
piece of code. What resizing never does is change **how much world you see**:
that is the framing, in world units, and it is the one display quantity the
simulation may read.

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

Every F-key is behind the flag. Without it they do nothing at all, and a key
that does nothing is indistinguishable from a bug — so pressing one shows a
transitory notice naming the flag once, and then stops. The flag itself is never
implied: a player who asked for no panels should get no panels.

Every dimension of the overlay is scaled by the same number as the world it
annotates (`WorldOverlayMetrics`), because the overlay is a description of the
world: an unscaled 1px hitbox outline arrives at 53% of its intent on a window
whose density is 1.889, and a debug layer that is too thin to see is not a debug
layer. Culling is `Camera.is_visible`, the one world-space cull in the
renderer — the overlay used to compare world rectangles against a target-pixel
rectangle, which rejects everything, so `F1` toggled a flag and drew nothing.

The overlay only draws what is on screen, which keeps the frame cost
predictable:

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
  default**: a level carries ~840 terrain tiles whose outline tells you
  nothing, and drawing them is the most expensive thing the overlay does.
  Measured on level 0 at 1280×720 with `DEBUG=1`, dropping the layer took
  the whole overlay pass from 1.98 ms to 0.09 ms — 1.9 ms of a 16.7 ms
  budget for a picture of the tileset.

### Frame timings

There is no always-on frame readout. It used to be two lines in the top-left
corner — `100.0 fps · 10.00 ms · limite 60`, then the four terms that make up
the frame — painted whether or not the debug overlay was on, and the whole
measurement ran on every frame of every session to feed it. It was a tool for
one question, and it answered that question badly enough to be noise the rest
of the time.

The `PERFORMANCE` panel under `DEBUG=1` carries what is still worth reading:
frame rate, frame time, the overlay and panel cost, sprite counts and the text
cache. Frame timing in general is `uv run pytest tests/benchmarks/ui_benchmark.py`.

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
and five pixel densities and compares a world checksum.

How large the world is *drawn* is a separate question, and its answer is the
**window**: the render target is the window's own letterbox rectangle, so a world
unit gets `window / framing` pixels — 1.667 at 1920x1080, 0.694 in an 800x600
window — and the art is magnified once, at load. The finished frame is then
blitted 1:1, so the picture is never resampled and cannot be softened by a
setting. The camera has no zoom; it has a density, and it reads it off the
target so the two cannot disagree.

| Object | What it is |
|---|---|
| `Framing` | the visible rectangle of the world, in world units. Fixed. |
| `Viewport` | the surface everything is drawn into: the window's letterbox rect |
| `Stage` | the OS window: mode, position, DPI, vsync. No opinion about size. |
| `Presentation` | window onto target, and the pointer back. Scales nothing. |

The invariant the four rest on: **the simulation reads `Framing` and nothing
else.** Window size, DPI, display mode and desktop dimensions are not
observable from it.

What follows from that:

- `Camera.apply()` maps a world rectangle to exact target coordinates —
  `screen = (world - offset) * density`. Sprites, health bars, hitboxes, labels
  and the debug overlays all read the one transform, so none of them can drift
  from the others;
- `Camera.scaled_size()` is the **single rounding rule** in the drawing path: an
  image is magnified to that size and blitted into a rectangle of that size.
  `Camera.apply_snapped()` is the matching position, rounded *down*, and the size
  rounds *up* — which is what makes a run of tiles overlap by at most a pixel
  instead of drifting apart by one every few tiles and opening a line of
  background through the terrain. `pygame.blit` silently resamples a source that
  does not fit its destination, so "off by a rounding" is a real defect here and
  not a cosmetic one; fuzzing every framing, density, offset and rect finds no
  gap and no resample;
- `Camera.is_visible()` culls against the framing rect, and the frozen terrain
  is narrowed to a handful of chunks before it gets there;
- every frame is a complete repaint of the target, so a stale pixel is not
  possible rather than merely unlikely;
- a window resize rebuilds the target, re-reads the density and re-lays out the
  interface — one cascade, shared with a display change. It never changes how
  much world is visible;
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

Coverage — CI enforces an 80 % instruction threshold (currently **90 %**):

```bash
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

Branch coverage is measured separately (currently **76 %**) and is *not*
compared against the instruction percentage:

```bash
uv run pytest --cov=src --cov-branch --cov-report=term-missing
```

The figures quoted in the badges, the summary table and the baseline block at
the end of this section are the output of the two commands above.
`tests/unit/test_readme_claims.py` re-checks the test count on every run
(`pytest --collect-only` costs under a second) and checks that the three
places quoting a coverage pair still agree with each other, so the numbers
cannot drift apart silently. The mypy file counts come from
`uv run mypy src main.py tools` and `uv run mypy src`.

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

> **Current baseline:** 2100 tests passing · 93 % instruction coverage ·
> 85 % branch coverage · Ruff clean · mypy clean (168 files across
> `src main.py tools`, the CI command; `mypy src` alone is 165). Tests run headless
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
│   ├── rendering/ Camera (fixed framing + a density read off the target), renderer,
│   │              and the tile chunk index that culls the frozen terrain
│   ├── display/   Framing, letterbox, Viewport, Stage, Presentation, detection
│   ├── rollback/  Snapshot ring buffer and deterministic restore
│   ├── rendering/ Camera, renderer, tile chunk index, world-overlay port
│                   Asset library and animator (`core/asset_library.py`)
│                   Audio bus (`core/audio.py`)
├── combat/        Frame data, hit resolver, knockback, charge and combo
│                  tracking (CombatSystem lives in core/level/systems/)
├── entities/      Entity base, player + controllers, projectiles, vitals
│   └── enemies/   Data-driven configs, factory, per-type behaviour
├── physics/       Collisions, gravity, movement, spatial hash, entity grid
├── states/        State machines (player, enemies, shared reactions)
├── ui/            Player HUD, panels, world-space debug overlay
│                 (dimensions in `world_overlay_metrics.py`, health bars in
│                 `world_overlay_bars.py`)
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
- The world is drawn from three **planes**, split by one property: whether the
  sprite moves. The tile layers are built once and never move, so they live in
  `SpriteGroups.static_sprites` and `fg_sprites` and are culled through
  `TileChunkIndex`, a chunk grid built once at load; everything that moves is
  in `all_sprites` and is scanned, which is exact and cheap because it is tens
  of sprites. The split is what makes the index pay: leaving the tiles in
  `all_sprites` would force the renderer to walk all ~840 of them every frame
  just to discover it had already drawn them. Anything that genuinely wants the
  whole world — the debug overlay, the sprite counter — reads
  `SpriteGroups.every_sprite` instead of one group, and the tile layers stay in
  `collision_sprites` as before, so physics is untouched. The index decides
  which sprites are *worth asking about*; `Camera.is_visible` still decides
  which are drawn, so a chunk can over-select but never under-select.
  `tests/unit/test_tile_chunk_index.py` asserts that on the real level, and
  `render_benchmark.py` measures it: 0.22 ms against 0.28 ms for the scan on
  level 0, and 0.07 ms against 2.67 ms at 22 000 tiles.
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
- The interface reaches the world by **injection**, not by import. `Renderer`
  takes a `WorldOverlay` (`src/core/rendering/overlay.py`) and draws nothing
  beyond the world without one; `UIManager` implements it, and `Game.world_overlay`
  builds it once and hands it to the level. So `core` never imports `ui`: the
  renderer can be built to ask whether a tile is culled without standing up a
  font cache and a panel layout first, and a level transition no longer throws
  the previous interface — and every font it had cached — away. `GameplayScene`
  does name `UIManager` concretely, which is the point: `application` is where
  the two layers are allowed to meet. `tests/unit/test_layer_boundaries.py`
  enforces the direction, so the next convenient import does not put it back.

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
  geometry is defined once in `src/ui/world_overlay_metrics.py`, which every
  layer that draws a bar reads, and it reaches the renderer through the
  `WorldOverlay` port rather than by `core` importing `ui`. Two copies agree
  only until someone edits one. UI-only constants (`HUD_PIP_SIZE`,
  `HEALTH_BAR_*`) stay in their UI module, and renderer internals
  (`DASH_STRETCH_*`) stay next to their only user.
- **One table for the interface.** `src/ui/metrics.py` holds every layout
  dimension of the menus as a `DESIGN_*` constant, and `Metrics` is the only
  thing that multiplies one by a scale. A view may not contain a layout
  literal: paddings, gaps, row heights and the panel border all come from a
  token. The reason is not tidiness — at a window density of 1.889 the grid used
  to pair a 49px font with 34px rows, so a clickable band covered 44% of the
  label above it and clicking the row you read activated the row above.
- **A row is never shorter than its text**, at any scale, in any window. A list
  that does not fit gives up *font size* (down to `MIN_TEXT_RATIO`) instead,
  because smaller text is still readable while an overlapping row is not
  clickable at all. `GridView` measures the real fonts rather than trusting the
  design constants, since a fallback face has different metrics again.
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
