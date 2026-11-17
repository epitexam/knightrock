# Knightrock

> A 2D hack 'n' slash platformer in Python with
> [pygame-ce](https://github.com/pygame-community/pygame-ce) — frame-data combat,
> a deterministic fixed-timestep simulation, data-driven gameplay values and a
> built-in debug test bench.

[![Python](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5.7%2B-2ea44f)](https://github.com/pygame-community/pygame-ce)
[![tests](https://img.shields.io/badge/tests-3735%20passing-brightgreen)](#tests--quality)
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
| **Hack 'n' slash combat** | No More Heroes 2 in 2D: high and low slashes against high and low guards, a blade battery to recharge by hand, beats that stun and throws, death blows on a direction prompt, a slot machine, blade locks, a dark step that slows the world and a fury gauge that opens the dark side -- on frame data with startup / active / recovery phases and multi-hitbox attacks. |
| **Deterministic physics** | Fixed 60 Hz simulation, sub-stepped swept collisions, moving platforms, one-way platforms, spatial hashing. |
| **Data-driven design** | Attacks, enemies, the player and the level registry live in tracked JSON, validated with strict errors; the attacks, enemies and player have no copy in code. |
| **Scene stack** | Menu, level select, options, video, controls, gameplay, pause, game-over and victory scenes over a synchronous, ordered [event bus](#architecture). |
| **Interface sounds** | One bus owns `pygame.mixer` and answers facts from the event bus (navigate, confirm, back). No screen names a cue or a file. Silent and non-fatal without a sound card. |
| **Debug test bench** | Hotkeys to spawn foes, fire pooled projectiles and force showcase attacks — no recompilation, no code edits. |
| **Quality gates** | 3735 tests, strict mypy and Ruff (lint, format, `C901`), all blocking in CI. |

---

## Controls

**Keyboard**

| Action | Key |
|---|---|
| Move | `Left arrow` / `Right arrow` |
| Low stance (ground) / fast fall (air) | `Down arrow` |
| Jump | `Space` |
| Dodge (passes through enemies) | `Left Shift` |
| Guard (held); with Down, recharge the battery | `Q` |
| Reset position (debug builds only) | `R` |
| Slash (hold to charge) | `A` |
| Punch / kick (hold to charge); throw a stunned foe | `S` |
| Shoot (hold to charge) | `D` |
| Dark side (with a full fury gauge) | `G` + `H` |
| Pause / resume | `Esc` / `Enter` |
| Menu navigation | `Enter` / `N` |
| Back in menus | `Esc` / right click |

**Gamepad** — the Xbox One layout, as SDL numbers its buttons

| Action | Button / axis |
|---|---|
| Move | Left stick (axis `0`) or D-pad (`0`) |
| Low stance / fast fall | Left stick (axis `1`) or D-pad (`0`) |
| Jump | `A` (`0`) |
| Slash (hold to charge) | `X` (`2`) |
| Punch / kick (hold to charge); throw | `Y` (`3`) |
| Shoot (hold to charge) | `B` (`1`) |
| Guard; with Down, recharge | `LB` (`4`) |
| Dark side (with a full fury gauge) | `X` + `Y` |
| Dash | Axis `2` (left trigger on Linux) |
| Reset position (debug builds only) | `View` (`6`) |
| Pause / resume | `Start` (`7`) |
| Menu navigation / confirm | Left stick or D-pad / `A` |
| Back in menus | `B` |

`B` is *Back* in the menus and the shot in the game, and it never pauses: the
pause is `Start` on the pad and `Esc` on the keyboard. A settings file still on
the previous default layout is moved to this one when it is read; a layout the
player built is kept, with the reset moved off `Start`; a file from before the
shot gets it on `B` and `D` unless something else is already there. Axis numbers are the
joystick API's and differ by platform: on Windows axis `2` is the right stick's
X, and the dash can be rebound from *Options → Controls*.

Three details of the menu navigation, all in `src/core/settings.py` under
`Input`:

- **A stick is a position, not a press.** A quarter of its travel moves one row;
  pushing further *scrolls*, and easing back stops it without stepping backwards.
- **The D-pad has no partial travel to read**, so holding it scrolls on its own.
- **Only the four directions auto-repeat**, stick and D-pad included — a held
  confirm would otherwise open and close a menu in a loop.

---

**Moves.** Three attack buttons -- the blade, the body and the shot -- the
first two thrown high, or low with Down held, and all three charged when held.
What a press throws depends on what the fighter is doing
(`src/entities/attack_moves.py`, chains in `data/gameplay/attacks.json`):

| Input | Move |
|---|---|
| Slash ×4 | `slash_high_1` cut down → `_2` backhand → `_3` thrust that steps in → `_4` heavy vertical cut (finisher). Down switches any link to its low twin: knee cut, low backhand, low thrust, and a rising cut that launches |
| Slash held | let go early: `charged_slash`, a wide cut that breaks a guard, harder with the time held. Held to the end: `charged_slash_full`, a bigger cut that throws a crescent forward |
| Beat ×3 | `punch_1` jab → `punch_2` cross → `punch_3` uppercut (launches); fills the stun gauge |
| Down + beat ×2 | `kick_1` sweep at the ankles → `kick_2` roundhouse that sends the foe into the wall |
| Beat held | `charged_kick`: goes through guards and armour, pushes hard |
| Shoot | `shot`: a short bolt fired from the blade for `Battery.SHOT_COST`; it breaks a wind-up from out of reach |
| Shoot held | `piercing_shot`: a bolt that goes through every guard and every foe on its line |
| Beat on a stunned foe in front, on the ground | the throw: a run of directions, then `throw` |
| Down + slash over a downed foe | `stab`: kills it |
| Slash during a dash, or just after | `dash_slash`: a cut across at full stretch that keeps the dash's speed |
| A slash that would kill | the foe is doomed: one direction, then `death_blow` |
| Slash / beat / shoot in the air | `air_slash` / `air_kick` (dive) / `air_shot` |

Every strike is sized to the drawn fighter (about 24 × 33 inside a 40 × 56
hitbox): a blade about 28 long from the shoulder, a fist about 22, a leg about
26; nothing reaches more than 48 in front or swings more than 150°, a high blow
stays above the hips and a low one starts below them, and no two moves of one
fighter share shape, timing, height and push (`tests/unit/test_move_proportions.py`).
A charge grows what it throws: at the charge multiplier `m` (1 let go at once, 2 held to the end) the blow hits `m` times harder, pushes and stuns `m` times more, and its shape and reach are `1 + Combat.CHARGE_REACH_GAIN × (m − 1)` times the uncharged one's; a full charge keeps that power and adds its tier's extra (the crescent, the pierce). A charged shot grows the same way. The blade and the body are two kinds of blow: the blade is quicker, longer and pushes little; the body starts later, freezes longer on a hit, pushes hard, stuns and goes through guards (`tests/headless/test_charge_and_buttons.py`).
A phase can launch a shot as it turns active (`launches`, from
`src/entities/shots.py`): the bolt, the piercing bolt, the crescent of a full
cut, the slime's lobbed glob.

**Enemies.** Each fighting type has its own moves: the goblin's two claws (an
overhead swipe, a low reach), the tooth's bite at the head and snap at the
ankles, the shell's shoulder bash and a roll along the floor that no guard
stops -- it is jumped -- and the slime's slam and spat glob, which lands low.

**What is drawn** (`src/core/rendering/strike_trails.py`, render only): a blade
cuts a thin crescent, a heavy cut a wider one; the body leaves a short streak
and a knuckle or a heel; a charged cut is gold and brighter the longer it was
held, a full one white-hot with afterimages; the death blow is dark red. A
held button gathers a ring at the hand that closes as it fills and flashes when
full. An enemy winding up shows a chevron at the height it will strike -- red,
or violet when no guard stops it. A blow that lands leaves its mark at the tip: a sharp cut for the blade, a burst of lines for the body, a cut with a flash for a charged one, drawn over the struck fighter's flash. A dash leaves stamps of the fighter spaced by the distance covered (`Afterimage.SPACING`), pale at the back and cyan nearer the fighter, with speed lines behind it that outlast it a moment and a clap of air where it started; a dark step throws out a violet ring and tints the slowed world; a block throws up a shield of light on the side of the blow -- a crescent that pushes outward, a brief bubble, sparks off its face -- gold for a perfect block.

A link of a chain starts as soon as the previous one has hit, and a press made a
little early is kept for `Input.ATTACK_BUFFER_WINDOW` and played the moment it
can be.

**The combat loop.** Modelled on No More Heroes 2, in 2D (`src/core/settings.py`:
`Battery`, `Fury`, `Finisher`, `Throw`, `Clash`, `Slot`, `Stun`, `Rush`, `Guard`):

| Mechanic | Rule |
|---|---|
| **Guards** | An enemy that guards (`guards` in `enemies.json`) holds it high or low and switches now and then; a mark on its front edge shows which half. A slash at that height is stopped. Mid-combo it braces: the `Guard.BLOCK_AFTER_HITS`-th blockable blow in a row is stopped at its height, so the same slash mashed stalls. A blocked blow bounces off: the move ends, the player is pushed back (`Guard.DEFLECT_PUSH`), staggers for `Guard.DEFLECT_STAGGER` and pays `Battery.DEFLECT_COST`. The enemy answers with a counter thrown behind the guard until its recovery, which is the opening; a blade that meets the counter bounces off the same way and locks nothing. A punch, a kick or a charged slash breaks the guard for `Guard.BROKEN_TIME`. The player's guard is held and stops everything from the front, for `Battery.GUARD_COST`, except a blow that breaks it. |
| **Battery** | Every slash costs `Battery.SLASH_COST`; on an empty battery a slash does `Battery.EMPTY_POWER` of its damage. Guard + Down recharges it, standing open. |
| **Death blow** | A slash that would kill leaves the foe doomed at `Finisher.DOOM_HEALTH`. The fight slows to `Finisher.TIME_SCALE` and one direction is asked: given in time, the death blow lands, fills fury and spins the slot machine. Missed, the foe gets back up with `Finisher.RECOVER_RATIO` of its health. |
| **Stun and throw** | Beats fill the stun gauge (the strip under an enemy's health bar). A stunned foe in front is grabbed with the beat button: `Throw.STEPS` directions, then the throw, which kills. A wrong one leaves the player open. |
| **Downed** | A launched foe lies on the ground for `Combat.DOWNED_DURATION`; a low slash over it is the stab that ends it. |
| **Blade lock** | Two blades that meet (`clash` on both hits) lock: mash the slash `Clash.PRESSES` times in `Clash.WINDOW` and the foe is thrown off balance (`Clash.WIN_STAGGER`) with its guard down for `Clash.WIN_OPEN` -- an opening, not a stun; lose, and it costs health. A counter never locks (see Guards). |
| **Dash** | One length whatever the stick (about 80 to 105 px): a burst from `Physics.DASH_SPEED` that eases out as `(1 - t)^Physics.DASH_CURVE` to the run speed when the stick holds its way -- so it hands over to the run without a stop -- or to a short glide when it does not. A push the other way in the first `Physics.DASH_REVERSE_WINDOW` turns it round, once, and no ground pivot can cut it short. Untouchable throughout; three charges, and spending the last locks it for `Physics.DASH_PENALTY_TIME`. |
| **Dark step** | A dodge less than `Rush.WINDOW` before a blow lands -- on the player, or on the spot the dodge left -- slows everything but the player for `Rush.DURATION`; slashes are free and fast meanwhile. |
| **Fury** | Filled by landing hits, death blows, throws and dark steps; a hit taken costs `Fury.HURT_LOSS`. Its tiers (`Fury.TIERS`) speed the slashes up -- the HUD combo counter gains a `!` per tier. Full, the chord opens the dark side: `Fury.DARK_DURATION` seconds untouchable, faster, every blow a kill. |
| **Slot machine** | Each death blow spins three reels; three of a kind (`Slot.JACKPOT_CHANCE`) grants a power for `Slot.POWER_DURATION`: stasis (the world slows, every blow kills), blitz (faster, every blow kills) or cleave (slashes `Slot.CLEAVE_MULT` harder). |

During a prompt the player is untouchable and the fight around it nearly
stops. Every `Combat.COMBO_DASH_REFILL_HITS` hits of one combo give a dash
charge back, and a hit landed out of a dodge refunds it.

## In-game options

Options is a **navigation hub**, not a list: every setting lives in the screen
that owns it. Reachable from the main menu and from the pause screen.

| Screen | Owns |
|---|---|
| **Video** | The window's size, how the picture fits the window (bars / whole-pixel / zoom), VSync, frame limit, UI scale, a read-out of what the game derived from the window, and — only under `DEBUG=1` — a debug panel scale. Settings with more than a few values open a **list** rather than cycling on ←/→, and each entry says what it does. |
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
| `1` `2` | Slash finishers | `slash_high_4`, `slash_low_4` |
| `3` `4` | Beat finishers | `punch_3` (uppercut, launches), `kick_2` (roundhouse, into the wall) |
| `5` | Charged slash | `charged_slash` — breaks a guard |
| `6` | Stab | `stab` — kills a downed foe |
| `7` `8` | Finishing moves | `death_blow`, `throw` — kill a helpless foe |
| `9` `0` | Air kit | `air_slash`, `air_kick` — **in the air only** |
| `V` | Projectile | plain `firebolt`, reuses `HitResolver` |
| `B` | Piercing projectile | passes through, hits each target once |
| `C` | Juggle dummy | pops an airborne dummy in front of the player |
| `G` `P` `T` | Spawn | goblin · slime · dummy |

<details>
<summary><b>Suggested juggle protocol</b></summary>

Press `C` to pop an airborne dummy, slash it in the air with `A` during the
jump, then `6` -- the stab -- once it lands.

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
> tileset. (`docs/audit/final-report.md`, §12)

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
uv run python tests/benchmarks/combat_feel.py      # how the combat plays: swings/s, kill times
```

---

## How it works

### Framing

> **The camera shows a fixed rectangle of the world: 1152×648 world units**
> (`src/core/display/framing.py`). It is render-only, and **the simulation reads
> it and nothing else** — window size, DPI and desktop dimensions
> are not observable from it.

It is deliberately tight: the player sees 45 % of the width and 34 % of the
height of the shipped level, so a level has to be read as it is entered rather
than mapped from the menu.

| Object | What it is |
|---|---|
| `Framing` | the visible rectangle of the world, in world units. Fixed. |
| `Viewport` | the surface everything is drawn into: the window's fitted rect |
| `Stage` | the OS window: size, monitor, DPI, vsync |
| `Presentation` | window onto target, and the pointer back. Scales nothing. |
| `monitors` | what this machine has, and which panel holds the window |
| `sdl_probe` | the libSDL2 pygame already links, for what pygame cannot say |

How large the world is *drawn* is a separate question, answered by the window: a
world unit gets `window / framing` pixels — 1.667 at 1920×1080, 0.694 in an
800×600 window — and the art is magnified once, at load. The camera has no zoom;
it has a density, read off the target so the two cannot disagree.

**More than one screen is a first-class case.** pygame-ce reports display
*sizes* and nothing else, which is why the window used to be pinned to the
primary: the other screens' origins were described as unknowable. They are not
unknowable, they are one layer down — `sdl_probe` reads the bundled SDL2 through
`ctypes` (stdlib only) and gets each display's bounds, the area a taskbar leaves
free, the name the platform gives it, its refresh rate and the compositor's
scale. Measured on the development machine:

```
pygame       SDL_GetDesktopSizes()   -> [(1920, 1080)]
SDL          SDL_GetDisplayBounds(0) -> (0, 0, 1920, 1080)
SDL          SDL_GetDisplayUsableBounds(0) -> (0, 32, 1920, 1048)
SDL          SDL_GetDisplayName(0)   -> b'eDP-1 17"'
```

The probe is cross-checked against pygame's own numbers and thrown away if they
disagree — `find_library` can hand back a second libSDL2 whose video subsystem
was never initialised, and it answers with plausible numbers describing nothing.
When it cannot be reached the game runs on what pygame can say, which is what it
did before.

**The game is a window, full stop.** There is no display mode, no exclusive
fullscreen, no borderless and no screen picker: the window is the render target
and the player chooses how big it is. Three rules replace all of that:

- the window opens **centred on the screen the last session closed on**, or on
  the primary display when that screen is not there, at the size the player
  chose or as large as fits the panel when they have not chosen one, and the
  player drags it from there. The screen is remembered by its name, so a
  settings file carried to another machine matches nothing and falls back to the
  primary. Where the window sits belongs to the window manager, which is why
  there is still no row claiming a screen and no stored position: a placement
  the game cannot guarantee is a setting it must not offer;
- the **render target is the window** — more precisely the fitted rectangle of the
  window that carries the picture at the framing's aspect. The finished frame is
  blitted **1:1**, so presenting costs a copy rather than a resample;
- **how the picture fits is the player's choice**: bars, whole-pixel art (each art
  pixel an exact *k*×*k* block, bars taking the rest), or zoom to fill, which crops
  the overflow. All three show *at most* the framing — zoom shows strictly less,
  so a video setting can never show more level than another. The HUD is laid out
  in the part of the target the window shows (`Game.shown_area`), so under zoom
  the gauges sit on the corners the player sees, not on the cropped-off ones.

Resizing the window rebuilds the render target, re-reads the pixel density and
re-lays out the interface — the same cascade as a window rebuild, which is why it
is one piece of code. What resizing never changes is **how much world you see**.

A resize is **read off the window, not off an event**: pygame-ce turns one SDL
window event into seven of its own, and which of them carries the new size depends
on the platform *and* on the gesture — measured, a snap reports `WindowSizeChanged`,
a maximise reports three events, a drag reports `VideoResize`. The size is polled
once per frame (0.07 µs), and the frame in which it changed lays the interface out
**before** the input is read. That ordering is the whole fix for "the clickable
area moved": a click is converted through the picture in force *now* and hit-tested
against the rectangles the last draw produced, and after a resize those two
disagreed — measured, by 244 px, so a click landed on a neighbour or on nothing.
`reset_cache` drops the rectangles too, covering the one case the runtime cannot
see coming: a change the game performs *while* handling an input, with a second
input already queued behind it in the same frame.

The screen the game reports — the VSync row's rate — is the screen **the window
is actually on**, found from its position rather than from the primary. When the
window's screen cannot be established, the row says nothing rather than the
primary's rate: a missing hint is recoverable, a wrong number is a fact.

Plugging a screen in or out mid-session is noticed: pygame-ce surfaces no event
for a display appearing or disappearing, so the display list is re-read on a timer
and a window whose screen has gone is rebuilt on the primary and says so.

<details>
<summary><b>Why the window's size is only a request, and why the framing is not derived from the window</b></summary>

**A size is asked for, not asserted.** A hardcoded list of window sizes is a
claim about the player's monitor the game cannot check — offering 2560×1440 to a
1366×768 laptop is what that costs. The sizes the menu offers are derived from
the panel in force and filtered to what it can hold, and the choice is only ever
*asked for*: the window manager grants it and the stage measures back what it
actually got, so the row reports the window rather than the request.

**The window's remembered size is a request, not an assertion.** It is honoured
where it fits and clamped where it does not, and the file keeps what the player
chose — so a 4K window arrives at a laptop shrunk to fit and comes back at 4K on
the next launch on a desk with the room. The old `width`/`height` keys were
*overwritten* at launch whenever they did not fit, which is why a size could never
survive a change of machine and why the menu and the screen used to disagree.

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

Source: `docs/audit/final-report.md`, §12.

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
- A frame drawn between two ticks blends the camera *and* the fighters by the
  same `alpha`: each fighter is drawn between where the last tick began and
  where it ended (`RenderHints.previous_center`, written at the top of every
  tick, frozen ones included). A move longer than `Interpolation.MAX_STEP_PX`
  is a teleport and is drawn where it lands. Health bars follow the drawn
  fighter. `Interpolation.ENABLED = False` turns it off.

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

### Combat and knockback

Combat is frame-data driven: startup / active / recovery phases feed
`HitboxManager` and `HitResolver` through the two-pass deterministic
`CombatSystem` (`src/core/level/systems/combat_system.py`).

| Constant | Effect |
|---|---|
| `Combat.WALL_BOUNCE_FACTOR` | Mid-launch entities rebound off walls (red arrow in debug) instead of stopping dead. |
| `Combat.GROUND_BOUNCE_MIN_SPEED` / `_FACTOR` / `_KEEP` | A launched fighter that lands faster than `MIN_SPEED` rebounds once, keeping `FACTOR` of its fall and `KEEP` of its run. `FACTOR = 0` turns it off. |
| `Combat.KNOCKBACK_MAX_DURATION` | Anti-lock safety for pits. |
| `Physics.REACTION_SLIDE_FRICTION` / `_SLIDE_DRAG` | How a hit fighter slides to a stop on the ground: a constant grip (px/s²) plus a drag (1/s). Shared by hurt, stagger and knockback, so a hit's `power` alone decides how far it sends its target. |
| `Physics.REACTION_AIR_DRAG` | Light horizontal drag while a hit fighter is airborne; `0` keeps the launch speed constant. |
| `Combat.KNOCKBACK_DI_ACCEL` / `_DI_CAP` | Directional influence: an airborne entity can steer its trajectory. |
| `Combat.JUGGLE_DECAY_STEP` / `JUGGLE_DAMAGE_FLOOR` | Diminishing returns on consecutive juggle hits. |
| `Combat.HITSTOP_KNOCKBACK_FACTOR` | Hit-stop scaled to impact magnitude. |
| `Combat.KILL_HITSTOP` / `EXECUTION_HITSTOP` | The least a killing blow, and an execution (a stab, a throw, a death blow), freeze the world. A hit's own `hit_stop` in `attacks.json` replaces the formula: the slash links freeze for two ticks, the finisher for seven. |
| `Combat.OTG_INVULN_DURATION` / `ENEMY_OTG_INVULN_DURATION` | How long a fighter landing from a launch is safe from ground hits: the player is, an enemy is not, so the blow after a launch lands. |
| `Combat.HEAVY_KNOCKBACK_THRESHOLD` | `400` — above it, `CameraShake` is given trauma of `impact / HEAVY_DIV`. |
| `CameraShake.HIT_TRAUMA` / `HIT_DIV` / `KILL_TRAUMA` / `EXECUTION_TRAUMA` | Every landed hit shakes a little, a kill a little more, an execution the most; the strongest of the tick wins. |
| `CameraShake` | `MAX_PX`, `DECAY_PER_S`, `FREQUENCY` — the shake envelope itself. |

Three things decide how far a hit sends its target, and nothing else does:

- the hit's `knockback.power` in `attacks.json` — the speed it gives, in px/s;
- the target's `weight` in `enemies.json` — every knockback it takes is divided
  by it, *before* the launch threshold is read, so one blow launches a slime
  (`0.8`), shoves a goblin (`1.0`) and barely moves a shell (`1.5`);
- the shared friction above (`Physics.REACTION_*`), the same in hurt, stagger
  and knockback.

A hit marked `flinch` in `attacks.json` does not push a grounded target
sideways: the chains' links stun without sending the target out of reach.
An airborne target is pushed as usual, so a juggle still carries.

An enemy the last hit kills leaves the simulation on that tick, and a body in
the FX plane (`CorpseParticle`, tuned by `fx.tuning.Corpse`) carries the hit on:
thrown the way the blow pushed, tumbling, fading. Render-only — it collides with
nothing and no snapshot or golden sees it.

**Enemies choose and take turns.** An enemy type lists its `moves` in
`enemies.json` -- an attack, the range it is thrown from and a weight. The chase
picks one on entry (from the enemy's own random stream, so a rollback replays the
choice) and closes in until it is in range. No more than `AI.MAX_ATTACKERS`
enemies attack the player at once: the others wait at striking distance, which
is counted from the roster's states each time and stored nowhere. The goblin and
the tooth add a long claw that sweeps the floor, the slime a splash: both can be
jumped. The goblin's swipe meets a slash blade to blade (`clash` on both hits).

**A slowed world is the same world on a slower clock.** During a dark step, a
prompt or stasis, the physics stage hands every entity but the player a share
of the tick's delta (`Player.world_time_scale`, `PhysicsSystem.process`), as do
the platforms, the hazards and the projectiles; attacks count frames off that
delta, so an enemy's swing takes that much longer. Fury, the dark side and
blitz do the reverse: the player's attack clock runs fast, and the surplus
frames are spent on the startup and the recovery only -- an active frame is
never skipped, so a fast swing hits what a slow one would.

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
| `enemies.json` | Enemy configs, referencing attack sets by name or inlining them; `moves` lists the attacks the AI chooses between, `stun_max` and `stun_duration` are the stun gauge, `guards` whether the type holds a guard. |
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
├── application/   Composition root (game.py), scene stack, save game, settings store
│   └── scenes/    menu · level select · options · video · controls category ·
│                  controls · gameplay · pause · game over · victory
├── combat/        Frame data, hit resolver, knockback, charge and combo
│                  tracking (CombatSystem lives in core/level/systems/)
├── core/          Event bus, settings, paths, colors, object pool,
│                  hazards, sprites, sprite groups, asset library, audio
│   ├── animation/ Animator
│   ├── display/   Framing, letterbox, Viewport, Stage, Presentation, monitors, detection, sdl_probe
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
docs/              Audit reports, measurements, open points, design proposals
```

### Reading the code, module by module

| Module | Owns |
|---|---|
| `src/application/game.py` | The display, the input and the scene stack. The loop feeds fixed ticks to the active scene, draws into the render target and presents it once. |
| `src/core/level/systems/gameplay_loop.py` | The *order* in which the level systems run. `GameplayLoop` requires every stage, so a loop that exists can run a tick; `CombatLoop` is the combat core alone, for tests. |
| `src/core/events.py` | A synchronous, strictly ordered event bus with two families of facts: simulation milestones (`LevelStarted`, `PlayerDied`, `LevelCompleted`, emitted from the fixed tick by a `Level` that holds no reference to the application) and interface feedback (`UiFeedback`, emitted by the input dispatcher from what a screen reports). Subscribers must never mutate the simulation. |
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
- **Comments say why, commits say how it got here.** A docstring states what the
  code does and why the rule exists; a body comment explains an invariant or a
  choice that is not obvious. The history -- what it used to do, a measurement
  from one session, an audit identifier -- goes in the commit message or in
  `docs/`, where it cannot go stale next to code that has moved on.
- **Stand-ins have the real shape.** A test double for a fighter starts from
  `tests/fakes.py` (`BodyStub`, `FighterSprite`, `player_shape`, `game_shape`),
  which is pinned to the protocols it imitates. Production code does not read a
  declared field through `getattr(x, name, default)` to tolerate a partial fake.

---

## Tests & quality

```bash
uv run pytest
```

> **Current baseline:** 3735 tests · 94 % instruction coverage · 84 % branch
> coverage · Ruff clean · mypy clean (184 files across `src main.py tools`;
> `mypy src` alone is 181).[^coverage]

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
`select` list consumed by the lint step. Ruff covers all four paths, 369 files.

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
| `docs/audit/current-architecture.md` | The architecture as it is (2026-11-12): layers, tick order, combat, AI and animation flows. |
| `docs/audit/comprehensive-audit.md` | The audit: verified defects C1-C5, every subsystem classified (keep, refactor, simplify...). |
| `docs/audit/architectural-recommendations.md` | The recommendations, the alternatives weighed, the target architecture. |
| `docs/audit/refactoring-roadmap.md` | The staged roadmap the refactoring followed. |
| `docs/audit/final-report.md` | What was changed, preserved, verified, the debt left, and the open points kept from the old notes. |
| `docs/audit/combat-dynamism.md` | Why the combat lacked pace, measured, the first reworks (§8-§11), and the full No More Heroes 2 rework (§12). |
| `docs/design/matrice-niveaux.md` | Proposal, not implemented: a world of rooms laid out as a matrix. |

---

[^coverage]: Measured on this commit. `tests/unit/test_readme_claims.py` checks
    that the figures agree with each other, not that they agree with a run.

[^mypy-tests]: Adding `tests/` to the mypy gate means first paying roughly 1400
    errors across 122 files of intentionally loose test doubles. That figure grows
    with every new test module — re-measure with `uv run mypy tests` rather than
    trusting it, and note that it is far higher under recent mypy releases than
    when it was first recorded.