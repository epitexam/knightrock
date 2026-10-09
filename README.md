# Knightrock

> A 2D hack 'n' slash platformer in Python with
> [pygame-ce](https://github.com/pygame-community/pygame-ce) — frame-data combat,
> a deterministic fixed-timestep simulation, data-driven gameplay values and a
> built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.7%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-2547%20passing-brightgreen)](#tests--quality)
[![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)](#tests--quality)
[![mypy](https://img.shields.io/badge/mypy-strict-blue)](#tests--quality)

## Quick start

Requires **Python ≥ 3.14** (`.python-version`) and [**uv**](https://docs.astral.sh/uv/).

```bash
uv sync --dev                    # --dev adds pytest, pytest-cov, ruff, mypy
uv run python main.py            # play
uv run python main.py --debug    # play with the debug overlay (DEBUG=1)
```

`--help` prints the usage. `uv run python main.py --debug` and
`DEBUG=1 uv run python main.py` are equivalent.

---

## Contents

- [What it is](#what-it-is)
- [Controls](#controls)
- [In-game options](#in-game-options)
- [Debugging](#debugging)
  - [Test bench](#test-bench)
  - [Debug overlay](#debug-overlay)
  - [Frame timings & benchmarks](#frame-timings--benchmarks)
- [How it works](#how-it-works)
  - [Framing](#framing)
  - [Camera, rounding and culling](#camera-rounding-and-culling)
  - [Physics and assists](#physics-and-assists)
  - [Combat and knockback](#combat-and-knockback)
  - [The ground pivot](#the-ground-pivot)
  - [Draw planes](#draw-planes)
- [Data-driven gameplay](#data-driven-gameplay)
- [Architecture](#architecture)
- [Conventions](#conventions)
- [Tests & quality](#tests--quality)
- [Packaging & releases](#packaging--releases)
- [Further notes](#further-notes)

---

## What it is

| Capability | What it does |
|---|---|
| **Frame-data combat** | Startup / active / recovery phases, chargeable heavies, combos, juggles, OTG guard and multi-hitbox attacks. |
| **Deterministic physics** | Fixed 60 Hz simulation, sub-stepped swept collisions, moving platforms, one-way platforms, spatial hashing. |
| **Data-driven design** | Attacks, enemies, the player and the level registry live in tracked JSON, validated with strict errors and safe fallbacks. |
| **Scene stack** | Menu, level select, options, video, controls, gameplay, pause, game-over and victory scenes over a synchronous, ordered [event bus](#architecture). |
| **Interface sounds** | One bus owns `pygame.mixer` and answers facts from the event bus (navigate, confirm, back). No screen names a cue or a file. Silent and non-fatal without a sound card. |
| **Debug test bench** | Hotkeys to spawn foes, fire pooled projectiles and force showcase attacks — no recompilation, no code edits. |
| **Quality gates** | 2547 tests, strict mypy and Ruff (lint, format, `C901`), all blocking in CI. |

---

## Controls

**Keyboard**

| Action | Key |
|---|---|
| Move | `Left arrow` / `Right arrow` |
| Crouch (ground) / fast fall (air) | `Down arrow` |
| Jump | `Space` |
| Dash (cancellable into an attack or guard) | `Left Shift` |
| Guard (tap = parry) | `Q` |
| Reset position | `R` |
| Attack 1 — light on the ground, aerial in the air | `A` |
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
| Move | Left stick (axis `0`) or D-pad (`0`) |
| Crouch / fast fall | Left stick (axis `1`) or D-pad (`0`) |
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

Three details of the menu navigation, all in `src/core/settings.py` under
`Input`:

- **A stick is a position, not a press.** A quarter of its travel moves one row;
  pushing further *scrolls*, and easing back stops it without stepping backwards.
- **The D-pad has no partial travel to read**, so holding it scrolls on its own.
- **Only the four directions auto-repeat**, stick and D-pad included — a held
  confirm would otherwise open and close a menu in a loop.

---

## In-game options

Options is a **navigation hub**, not a list: every setting lives in the screen
that owns it. Reachable from the main menu and from the pause screen.

| Screen | Owns |
|---|---|
| **Video** | Display mode, whole-pixel art, VSync, frame limit, UI scale, a read-out of what the game derived from the window, and — only under `DEBUG=1` — a debug panel scale. |
| **Controls → Menu controls** | Key/button rebinding and the menu stick Y inversion. |
| **Controls → Gameplay controls** | Key/button rebinding. |

Each controls screen ends on a separated, greyed block — the Y inversion,
**Reset to defaults** and **Back**. They are *choices*, not slots, so they carry
no key: a row that looks like the others and cannot take a binding is a row you
press a key on and nothing happens.

Choices are written to `~/.knightrock/settings.json` and apply without
restarting. Each sub-menu has its own **Reset**, restoring exactly what it owns —
the video one leaves your controls alone. A file that cannot be read is reported
in the log with its reason rather than silently replaced, and the file being
overwritten is kept as `settings.json.bak`.

---

## Debugging

Everything below is inert unless the game runs with `DEBUG=1` (or
`--debug`). Pressing an F-key without the flag shows a transitory notice naming
it once, then stops — a key that silently does nothing is indistinguishable from
a bug, but the flag is never implied either.

### Test bench

Every showcase feature is reachable from a single hotkey, live in game.

| Key | Feature | Detail |
|:---:|---|---|
| `1` | Multi-hitbox | `twin_fangs` — blade plus a second, disjoint box |
| `2` | Animated hitbox | `sweeping_arc` — the box grows along its keyframe curve |
| `3` | Juggle | `sky_launcher` — launches upward with softened gravity (`×0.5`) |
| `4` | OTG | `otg_slam` — the only attack allowed during the OTG guard |
| `5` | Extra shapes | `p5_shapes` |
| `6` | Radial burst | `circle_burst` |
| `7` `8` `9` `0` | Air kit | `air_attack`, `air_forward`, `air_rise`, `air_sweep` — **in the air only** |
| `V` | Projectile | plain `firebolt`, reuses `HitResolver` |
| `B` | Piercing projectile | passes through, hits each target once |
| `C` | Juggle dummy | pops an airborne dummy in front of the player |
| `G` `P` `T` | Spawn | goblin · slime · dummy |

<details>
<summary><b>Suggested juggle protocol</b></summary>

Press `C`, then `3` under the dummy (neutral, while airborne) to start the
juggle. Juggle mid-air with `A` during the jump, then finish on the ground with
`4` while the OTG guard is active.

Under `DEBUG=1` the overlay shows the offensive boxes plus `Combo (air xN)`,
`Juggle`, `OTG guard` and the `Shots` counter in the SCENE panel.

</details>

### Debug overlay

| Key | Layer / tool |
|:---:|---|
| `F1` | Hitboxes |
| `F2` | Labels |
| `F3` | Velocity arrows |
| `F4` | Static geometry — **off by default** |
| `F5` | Panels |
| `F6` | Freeze the simulation |
| `F7` | Step one tick (while frozen) |
| `F8` | Replay an attack |
| `F9` | Export it |
| `F10` | Next debug panel |
| `F11` | Panel layout — compact / full |

The full list is recalled on screen by the `DEBUG KEYS` panel.

**What the overlay draws.** Hitboxes are blue (player), red (enemy), grey
(neutral); overlaid with a green hurtbox and an orange offensive box. Velocity
arrows are a tapered shaft, a filled head and a pivot dot, all wrapped in a dark
rim so the silhouette survives a bright sky — the head length is clamped and
short vectors are stretched, so a walk and a dash both stay legible. The arrow
is **red** while the hit that caused it is fresh or while the knockback state
still carries the entity, **gold** on a parry, yellow for locomotion. Outlines:
cyan = OTG guard, purple = juggle gravity. Labels are short cards, with a second
line only during an attack or when a flag is set; projectiles carry speed,
lifetime and pierce; tiles are skipped. Multi-box indices are drawn as in-situ
vector points, the first filled and the following ones hollow.

**Everything is scaled by the density of the world it annotates**
(`WorldOverlayMetrics`), because the overlay is a *description* of the world: an
unscaled 1 px hitbox outline arrives at 53 % of its intent on a window whose
density is 1.889, and a debug layer too thin to see is not a debug layer. Culling
is `Camera.is_visible`, the one world-space cull in the renderer. Melee, projectile
AABB and moving-hazard geometry use **swept** collision; static hazards and
contact damage keep **discrete** collision.

> **Why `F4` ships off.** A level carries 839 terrain tiles whose outline tells
> you nothing, and drawing them is the most expensive thing the overlay does.
> Measured on level 0 at 1280×720, dropping the layer took the whole overlay pass
> from **1.98 ms to 0.09 ms** — 1.9 ms of a 16.7 ms budget, for a picture of the
> tileset. (`notes/perf_debug_overlay.md`)

### Frame timings & benchmarks

There is no always-on frame readout: the measurement used to run on every frame of
every session to paint two lines in the corner, which made it noise the rest of the
time. The `PERFORMANCE` panel under `DEBUG=1` carries what is still worth reading
— frame rate, frame time, overlay and panel cost, sprite counts, text cache.

```bash
uv run python tests/benchmarks/ui_benchmark.py       # frame timing, in general
uv run python tests/benchmarks/fx_benchmark.py       # cost to build one particle
uv run python tests/benchmarks/render_benchmark.py
uv run python tests/benchmarks/contact_benchmark.py
```

---

## How it works

### Framing

> **The camera shows a fixed rectangle of the world: 1152×648 world units**
> (`src/core/display/framing.py`). It is render-only, and **the simulation reads
> it and nothing else** — window size, DPI, display mode and desktop dimensions
> are not observable from it.

It is deliberately tight: the player sees 45 % of the width and 34 % of the
height of the shipped level, so a level has to be read as it is entered rather
than mapped from the menu.

| Object | What it is |
|---|---|
| `Framing` | the visible rectangle of the world, in world units. Fixed. |
| `Viewport` | the surface everything is drawn into: the window's letterbox rect |
| `Stage` | the OS window: mode, position, DPI, vsync. No opinion about size. |
| `Presentation` | window onto target, and the pointer back. Scales nothing. |

How large the world is *drawn* is a separate question, answered by the window: a
world unit gets `window / framing` pixels — 1.667 at 1920×1080, 0.694 in an
800×600 window — and the art is magnified once, at load. The camera has no zoom;
it has a density, read off the target so the two cannot disagree.

**The window is the only source of truth about the window.** There is no stored
size, no `size_mode`, no render scale and no smoothing flag, because none of those
describes a screen. Four rules replace them:

- the **display mode** defaults to *auto* — borderless when the screen already has
  the shape of the framing, a window otherwise, re-evaluated on every launch. A
  chosen mode is never re-resolved;
- a **windowed** game opens as large as fits with room for its own title bar, and
  that is all. Drag it to whatever you like;
- the **render target is the window** — more precisely the letterbox rectangle of
  the window that carries the picture at the framing's aspect. The finished frame
  is blitted **1:1**, so presenting costs a copy rather than a resample;
- **whole-pixel art** trades filling the window for every art pixel being an exact
  *k*×*k* block: the picture becomes the largest whole multiple of the framing
  that fits and the bars take the rest. It is a no-op below the framing size, and
  the row says so.

Resizing the window rebuilds the render target, re-reads the pixel density and
re-lays out the interface — the same cascade as a display change, which is why it
is one piece of code. What resizing never changes is **how much world you see**.

<details>
<summary><b>Why the video menu has no resolution row, and the framing is not derived from the window</b></summary>

**No resolution row.** A list of window sizes is a claim about the player's
monitor that the game cannot check, and a remembered size is a claim that goes
stale — in borderless the window *is* the screen's size whatever the file says,
so the row used to display a number the game was not using.

**The framing is not derived from the window.** It used to be built from the
window's pixel size and a zoom constant, which made the visible world a free
variable of a video setting: the reveal ran from 34 % of the level's height at the
smallest preset to 60 % at the largest, and on the 40×15 levels a high enough
preset revealed a whole level, height included. A player could see more of a level
by opening the video menu.

Two tests pin it now:

- `tests/unit/test_framing_contract.py` asserts the framing is smaller, on both
  axes, than every level in `data/levels_manifest.json`;
- `tests/unit/test_sim_is_display_independent.py` runs one input log at five
  window sizes and five pixel densities and compares a world checksum.

</details>

<details>
<summary><b>Measured: presenting 1:1 versus <code>smoothscale</code></b></summary>

Presenting the finished frame with a 1:1 copy, against resampling it to the same
target with `pygame.transform.smoothscale`:

| Window | 1:1 present | `smoothscale` |
|---|---|---|
| 1280×720 | ~0.38 ms | ~3.95 ms |
| 2560×1440 | ~1.33 ms | ~7.46 ms |

Sources: `notes/perf_shatter_arc.md`, `notes/audit_dimensions_fenetre.md`.

</details>

### Camera, rounding and culling

- `Camera.apply()` maps a world rectangle to exact target coordinates —
  `screen = (world - offset) * density`. Sprites, health bars, hitboxes, labels
  and the debug overlays all read the one transform, so none of them can drift
  from the others.
- `Camera.scaled_size()` is the **single rounding rule** in the drawing path: an
  image is magnified to that size and blitted into a rectangle of that size.
- `Camera.is_visible()` culls against the framing rect, and the frozen terrain is
  narrowed to a handful of chunks before it gets there.
- Every frame is a complete repaint of the target, so a stale pixel is not
  possible rather than merely unlikely.

<details>
<summary><b>Why the rounding rule is asymmetric</b></summary>

`Camera.apply_snapped()` rounds position **down** and size **up**. That is what
makes a run of tiles overlap by at most a pixel instead of drifting apart by one
every few tiles and opening a line of background through the terrain.

It is a real defect rather than a cosmetic one because `pygame.blit` silently
resamples a source that does not fit its destination. Fuzzing every framing,
density, offset and rect finds no gap and no resample.

</details>

### Physics and assists

Assists are **on**. Set a value to `0` (or `1` for the jump cut) to restore the
legacy, assist-free behaviour. All of them live in `src/core/settings.py`.

| Class | Constant | Effect |
|---|---|---|
| `GameFeel` | `JUMP_CUT_DIVISOR` | Variable jump height — releasing the button cuts the rise. |
| `GameFeel` | `GROUND_SNAP_PX` | Sticks to the ground instead of floating off platform edges. |
| `GameFeel` | `STEP_UP_PX` / `CORNER_CORRECT_PX` | Auto-mounts small steps, nudges around ceiling corners. |
| `GameFeel` | `APEX_GRAVITY_DIVISOR` | Reduced gravity at the jump apex, for a longer hang time. |
| `GameFeel` | `FAST_FALL_GRAVITY_MULTIPLIER` | Extra fall acceleration while the down key is held. |
| `Collision` | `MIN_PENETRATION_PX` | Grazes keep sliding instead of stopping dead. |
| `Collision` | `MAX_RESOLVE_PX` | Anti-teleport guard; deeper overlaps flag the entity `crushed`. |
| `PlatformRide` | `STICKY_FACTOR` | Stay mounted on fast-descending platforms. |
| `Physics` | `CROUCH_HEIGHT_FACTOR` | Crouched hurtbox as a fraction of the standing height. |
| `Physics` | `CROUCH_HEIGHT_BLEND_TIME` | Seconds to ease into and out of the crouched collider. |
| `Physics` | `CROUCH_SPEED_MULT` | Crouch-walk speed as a fraction of the fighter's own speed. |

> **The crouch constants live in `Physics`, not `GameFeel`.** They belong to the
> collider, not to the feel, and their only readers are
> `src/entities/crouch_posture.py` and `src/states/player_states.py`.

### Combat and knockback

Combat is frame-data driven: startup / active / recovery phases feed
`HitboxManager` and `HitResolver` through the two-pass deterministic
`CombatSystem` (`src/core/level/systems/combat_system.py`).

| Constant | Effect |
|---|---|
| `Combat.WALL_BOUNCE_FACTOR` | Mid-launch entities rebound off walls (red arrow in debug) instead of stopping dead. |
| `Combat.KNOCKBACK_MAX_DURATION` | Anti-lock safety for pits. |
| `Combat.KNOCKBACK_DI_ACCEL` / `_DI_CAP` | Directional influence: an airborne entity can steer its trajectory. |
| `Combat.JUGGLE_DECAY_STEP` / `JUGGLE_DAMAGE_FLOOR` | Diminishing returns on consecutive juggle hits. |
| `Combat.HITSTOP_KNOCKBACK_FACTOR` | Hit-stop scaled to impact magnitude. |
| `Combat.HEAVY_KNOCKBACK_THRESHOLD` | `400` — above it, `CameraShake` is given trauma of `impact / HEAVY_DIV`. |
| `CameraShake` | `MAX_PX`, `DECAY_PER_S`, `FREQUENCY` — the shake envelope itself. |

> **Directional influence is not player-gated.** `_apply_directional_influence` in
> `src/states/reaction_states.py` fires for any entity whose `move_axis` is
> non-zero, and enemies do set `move_axis`. In practice a launched enemy rarely
> carries a stale axis into the air, but the gate is "has an axis", not "is the
> player".

### The ground pivot

> **`turn` is a state, not a delayed facing write.** Reversing on the ground used
> to mirror the sprite on the same frame the axis flipped, so a pivot read as a
> teleport. The velocity curve was never the problem — it always took about a
> third of a second to cross zero. The picture refused to show any of it.

A delay would be a value every interrupter has to be told to undo, and each of
them would have to know the rule exists. A state is entered and exited, so an
attack, a dash or a jump taken mid-pivot leaves through `PlayerTurnState.exit` —
which is where the facing is finally committed. *"An attack inside the pivot
still comes out where the player is pointing"* is not a special case anyone has
to remember.

| Constant | Shipped | Effect |
|---|---|---|
| `Turn.DELAY_S` | `0.14` | How long the pivot holds — just under nine ticks at 60 Hz, the length of the plant. |
| `Turn.MIN_SPEED_PX_S` | `30.0` | Below this the fighter is not travelling, so the flip is immediate and no state is entered. |
| `Turn.BRAKE_CONTROL` | `20.0` | Ground braking on a reversal: bleed toward **zero** at this rate. |
| `Turn.PLANT_PX_S` | `20.0` | …then push out of the plant at this speed. |
| `Turn.LEAD_PX` | `32.0` | Render-only trailing offset of the body, shrinking to zero as the facing lands. |
| `Turn.SKEW_PX` | `20.0` | Shears the frame so the feet stay planted and the top of the body leans over. |
| `Turn.STEP_DISTANCE_PX` / `SPREAD` | `40.0` / `1.15` | The pivot's row in `FootstepDust.TIER`. |

**The pivot is registered in every fighter's state machine** under one shared name
(`Turn.STATE`), and activation is decided by **group and sub-group** rather than
by one entity at a time. Groups and sub-groups are named profiles in
`settings.PROFILES`, layered by inheritance; every field is optional, and a field
a layer leaves out is inherited.

| Layer | Where it is named | Ships as |
|---|---|---|
| defaults | `settings.Turn` | off |
| group (one per faction) | `PROFILES["player" / "enemy" / "neutral"]` | only the player is on |
| sub-group (one per enemy type) | `EnemyConfig.turn_profile`, i.e. `"turn_profile"` in `enemies.json` | `null` — takes the group |
| the entity | an attribute set in code | wins over all of the above |

<details>
<summary><b>Measured rationale, worked example, and two state details</b></summary>

**Why braking and accelerating are separate.** A single exponential ease toward
the target is symmetric by construction: the same rate bleeds speed off on the way
to a stop as on the way back up to a run. That is right for one and wrong for the
other. A *reversal* is not that — and a symmetric curve never plants, it crosses
zero without dwelling. At `Physics.FLOOR_CONTROL` a full run crosses in under two
frames, so the deceleration existed and was never seen. *"It turns instantly"*
means not that nothing happens but that what happens is over before the eye has it.

- **Brake toward zero, then plant.** From `PLAYER_SPEED`, a full run sheds
  `251 → 180 → 129 → 92 → 66 → 47 → 34 → 24 px/s` over the eight ticks of
  `DELAY_S`, arriving at the flip standing still.
- **Aiming at zero is the part that matters.** The rate only decides how fast the
  bleed is; aiming at the *target* makes the velocity curve pass through the
  crossing at any rate, so the plant never happens.
- **Airborne is untouched** — a mid-air reversal is a jump turn, and the tighter
  air curve is what makes an air dash feel like an air dash.
- **The lean carries the effect, not the slide.** `LEAD_PX` at 32 px is half the
  sprite's width — 5.5 frames of travel, clear and near its ceiling. A lean has no
  such ceiling, because it cannot detach from anything, which is why raising
  `SKEW_PX` paid far more than raising the slide would have.

**Worked example** — *"all the enemies except the slimes"*. Illustrative: the
repository ships the mechanism, not these entries.

```python
# src/core/settings.py — all the enemies take it...
PROFILES["enemy"] = TurnProfile(inherits="default", enabled=True)
# ...except this one, which plants more slowly and leans further.
PROFILES["enemy_goblin"] = TurnProfile(inherits="enemy", brake_control=12.0, skew_px=28.0)
PROFILES["enemy_slime"] = TurnProfile(inherits="enemy", enabled=False)
```

```json
// data/gameplay/enemies.json — which sub-group each type belongs to
{ "goblin": { "turn_profile": "enemy_goblin" } }
```

One entry on for the faction, one off for the type, one string in the type's
config. Nothing in the simulation, the state machine or the renderer knows a
group exists — an entity adopts a name and is done.

- **An unknown profile name is the defaults, not a crash.** A typo gives a fighter
  the shipped behaviour and a game that still starts; a self-inheriting profile
  stops at the cycle rather than hanging at import.
- **The drawing numbers travel with the profile.** `turn_lead_px` and
  `turn_skew_px` live on the entity, not in `settings.Turn`, because the renderer
  is handed a sprite. Left in the settings block they would make a group look
  tunable while the lean quietly ignored it.
- **Per-fighter overrides** win over every named layer: `turn_enabled`,
  `turn_delay_s`, `turn_brake_control`, `turn_plant_px_s`,
  `turn_min_speed_px_s`, `turn_lead_px`, `turn_skew_px`.
- **The hold is installed from the input side.** `PlayerInputHandler` reads input
  in `_pre_update`, *before* the state machine, so a decision taken from a state's
  own `update` would be a frame too late to stop the mirror it is meant to delay.
  `request_turn()` is asked instead of `face_movement()`, and the state keeps the
  mirror frozen with the `facing_locked` tag.
- **The pivot carries the tier it interrupted.** The hold spans the frames where
  the velocity sweeps through `run` / `walk` / `walk_slow`, so resuming from it
  with the live state name would drop `resolve_locomotion_state`'s hysteresis and
  flicker the tier boundaries at the fastest moment.

</details>

### Draw planes

The world is drawn from three **planes**, split by one property: whether the
sprite moves.

| Group | Contents | Culling |
|---|---|---|
| `SpriteGroups.static_sprites` | Background and terrain layers, built once | `TileChunkIndex`, a chunk grid built at load |
| `SpriteGroups.all_sprites` | Everything that moves | Scanned — exact and cheap, tens of sprites |
| `SpriteGroups.fg_sprites` | Foreground tile layers | `TileChunkIndex` |

That split is what makes the index pay: leaving the tiles in `all_sprites` would
force the renderer to walk all 839 of them every frame just to discover it had
already drawn them. Measured on level 0: **0.22 ms against 0.28 ms** for the scan;
at 22 000 tiles, **0.07 ms against 2.67 ms**. The tile layers stay in
`collision_sprites` as before, so physics is untouched.

Anything that genuinely wants the whole world — the debug overlay, the sprite
counter — reads `SpriteGroups.every_sprite` instead of one group. The index
decides which sprites are *worth asking about*; `Camera.is_visible` still decides
which are drawn, so a chunk can over-select but never under-select.

---

## Data-driven gameplay

Attacks, enemies, the player and the level registry live in **tracked JSON** under
`data/gameplay/`. These files are versioned — unlike `assets/` — so balance changes
are reviewable in a pull request. The frozen dataclasses stay the runtime model.

| File | Contents |
|---|---|
| `attacks.json` | Named attack sets (`player`, `goblin`, `slime`, …) with full frame data. |
| `enemies.json` | Enemy configs, referencing attack sets by name or inlining them. |
| `player.json` | Player overrides plus the name of the attack set to use. |
| `levels.json` | Level id to TMX path mapping. |

Loading is **strict**: unknown keys, missing fields, bad versions and unknown
attack references raise `GameplayDataError`. A *missing* file falls back to the
historical in-code values with a warning, so the game never refuses to boot over a
data problem.

**Environment variables**

| Variable | Purpose |
|---|---|
| `DEBUG=1` | Enable the debug overlay and hotkeys. Same as `main.py --debug`. |
| `KNIGHTROCK_DATA_DIR` | Alternate root containing `gameplay/*.json` (modders, tests). |
| `KNIGHTROCK_EXPORT_DIR` | Destination for `F9` attack exports (default `~/.knightrock/exports/`). |
| `KNIGHTROCK_SAVE_DIR` | Override the save directory (default `~/.knightrock/`). |
| `SDL_VIDEODRIVER=dummy` | Headless rendering (CI, automated tests). |
| `SDL_AUDIODRIVER=dummy` | Headless audio (CI, automated tests). |

---

## Architecture

```
src/
├── application/   Scene stack, event bus, save game, settings store
│   └── scenes/    menu · level select · options · video · controls category ·
│                  controls · gameplay · pause · game over · victory
├── combat/        Frame data, hit resolver, knockback, charge and combo
│                  tracking (CombatSystem lives in core/level/systems/)
├── core/          Bootstrap (game.py), settings, paths, colors, object pool,
│                  hazards, sprites, sprite groups, asset library, audio
│   ├── animation/ Animator
│   ├── display/   Framing, letterbox, Viewport, Stage, Presentation, detection
│   ├── fx/        Draw, particles, spawners
│   ├── input/     Bindings, providers, managers, input state
│   ├── level/     Level facade + ordered fixed-tick systems
│   ├── rendering/ Camera (fixed framing + a density read off the target),
│   │              renderer, tile chunk index, world-overlay port
│   └── rollback/  Snapshot ring buffer and deterministic restore
├── data/          Strict JSON loaders + in-code fallback values
├── entities/      Entity base, player + controllers, projectiles, vitals,
│                  crouch posture
│   └── enemies/   Data-driven configs, factory, per-type behaviour
├── physics/       Collisions, gravity, movement, spatial hash, entity grid
├── states/        State machines (player, enemies, shared reactions, turn)
└── ui/            Player HUD, panels, world-space debug overlay
                   (dimensions in `world_overlay_metrics.py`, bars in
                   `world_overlay_bars.py`, menus in `metrics.py`)

data/gameplay/     Tracked JSON gameplay values
assets/            TMX levels and sprites — required at runtime
notes/             Refactoring plans, audit reports, measurements, open gaps
```

### Reading the code, module by module

| Module | Owns |
|---|---|
| `src/core/game.py` | The display, the input and the scene stack. The loop feeds fixed ticks to the active scene, draws into the render target and presents it once. |
| `src/core/level/systems/gameplay_loop.py` | The *order* in which the level systems run. Each system stays independently testable. |
| `src/application/events.py` | A synchronous, strictly ordered event bus with two families of facts: simulation milestones (`LevelStarted`, `PlayerDied`, `LevelCompleted`, emitted from the fixed tick by a `Level` that holds no reference to the application) and interface feedback (`UiFeedback`, emitted by the input dispatcher from what a screen reports). Subscribers must never mutate the simulation. |
| `src/core/audio.py` | The only module that touches `pygame.mixer`, and it is a **consumer**: it never asks who did something and imports neither the input router, the menu model, the scenes nor the views. `cue_for(effect)` is the whole policy — one effect, one cue — and `attach(bus)` subscribes to the facts it answers. It loads each sound once, caches it, applies the cue's category volume and never raises: no sound card, no asset and an undecodable file all end with a warning and a silent cue, which is also the CI path. |
| `src/core/rendering/overlay.py` | The `WorldOverlay` port. `UIManager` implements it and `Game.world_overlay` builds it once. |

The **frame loop is paced exactly once**: with vsync off the `Clock` holds the
frame limit, with vsync on the present already blocks on the vertical blank, so the
clock is ticked only against a runaway ceiling derived from that rate. Targeting
60 on top of a 60 Hz present waits twice for one refresh and alternates between on
time and one refresh late. The ceiling is a backstop, not a frame rate control,
and it is derived rather than hardcoded so raising the limit can never leave it
underneath. `Display.FPS` is a build target that feeds that ceiling — *not* the
player-facing frame rate, which lives in `settings_store.FRAME_LIMITS`. A frame
runs at most `Simulation.MAX_TICKS_PER_FRAME` ticks and the surplus is dropped.

> **The interface reaches the world by injection, not by import.** The renderer
> takes a `WorldOverlay` and draws nothing beyond the world without one, so `core`
> never imports `ui`. `GameplayScene` does name `UIManager` concretely, which is
> the point: `application` is where the two layers are allowed to meet.
> `tests/unit/test_layer_boundaries.py` enforces the direction, so the next
> convenient import does not put it back.

---

## Conventions

- **Typed code.** `mypy src main.py tools` is blocking
  (`disallow_untyped_defs = true`, `disallow_incomplete_defs = true`) with **no
  per-module override left** in `pyproject.toml`. `tests/` is excluded, on
  purpose.
- **Formatted & measured.** `ruff format` for style, `C901` for cyclomatic
  complexity (threshold 10, every exception justified).
- **Deterministic simulation.** Fixed timestep
  (`Simulation.TICK_RATE = 60`). Nothing may introduce non-determinism into the
  tick.
- **Centralized tuning.** Gameplay constants live in `src/core/settings.py` — no
  magic numbers in the systems. A constant **shared by two modules has exactly
  one home**, and it belongs to the module that acts on it: HP-bar geometry is
  defined once in `src/ui/world_overlay_metrics.py`, which every layer that draws
  a bar reads, and it reaches the renderer through the `WorldOverlay` port rather
  than by `core` importing `ui`. Two copies agree only until someone edits one.
  UI-only constants (`HUD_PIP_SIZE`, `HEALTH_BAR_*`) stay in their UI module, and
  renderer internals (`DASH_STRETCH_*`) stay next to their only user.
- **One table for the interface.** `src/ui/metrics.py` holds every layout
  dimension of the menus as a `DESIGN_*` constant, and `Metrics` is the only
  thing that multiplies one by a scale. A view may not contain a layout literal.
  The reason is not tidiness: at a window density of 1.889 the grid used to pair a
  49 px font with 34 px rows, so a clickable band covered 44 % of the label above
  it and clicking the row you read activated the row above.
- **A row is never shorter than its text**, at any scale, in any window. A list
  that does not fit gives up *font size* (down to `MIN_TEXT_RATIO`) instead,
  because smaller text is still readable while an overlapping row is not clickable
  at all. `GridView` measures the real fonts rather than trusting the design
  constants, since a fallback face has different metrics again.
- **No dead menu options.** User-facing hotkeys are mirrored by tests.

---

## Tests & quality

```bash
uv run pytest
```

> **Current baseline:** 2547 tests · 94 % instruction coverage · 91 % branch
> coverage · Ruff clean · mypy clean (176 files across `src main.py tools`;
> `mypy src` alone is 173).[^coverage]

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
`select` list consumed by the lint step. Ruff covers all four paths, 328 files.

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

`tests/unit/test_readme_claims.py` runs as part of the suite and re-checks this
file: it recounts the collected tests and asserts that every test-count figure
here equals the real one, and that the coverage badge and the coverage pair agree
with each other. It checks internal consistency, not truth — keep this section in
sync when the numbers move.

---

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

---

## Further notes

Written in French unless stated otherwise.

| File | Contents |
|---|---|
| `notes/audit_consolide.md` | Consolidated code audit. |
| `notes/audit_ui.md`, `notes/audit_controles.md` | UI and input audits, with the delivery matrix and acceptance checklist. |
| `notes/ecarts_ouverts.md` | Open gaps and the measured reference baseline. |
| `notes/hitbox_amelioration.md` | Hitbox and advanced-combat work, with `notes/plan_hitbox_amelioration_partiels.md` for the partial-compliance follow-up. |
| `notes/plan_limit_frames_video.md` | Planned frame-limit setting for the video menu, with the measurements that bound it. |
| `notes/audit_p1_measured.md` | Measured rendering baselines behind the tile-chunk index numbers. |
| `notes/audit_dimensions_fenetre.md` | Window and sizing audit, with the `smoothscale` measurements. |
| `notes/perf_debug_overlay.md` | The overlay pass cost, with and without the static layer. |
| `notes/perf_shatter_arc.md` | Particle construction cost and the 1:1 present measurement. |
| `notes/refacto.md` | Refactoring plans and open threads. |

---

[^coverage]: Measured on this commit. `tests/unit/test_readme_claims.py` checks
    that the figures agree with each other, not that they agree with a run.

[^mypy-tests]: Adding `tests/` to the mypy gate means first paying roughly 1400
    errors across 122 files of intentionally loose test doubles. That figure grows
    with every new test module — re-measure with `uv run mypy tests` rather than
    trusting it, and note that it is far higher under recent mypy releases than
    when it was first recorded.