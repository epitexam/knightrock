# Architecture and rendering

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
| `Presentation` | window onto target, and the pointer back. At a reduced render scale it upscales the finished frame to the window. |
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
- the **render target is the window's fitted rectangle** at the default render
  scale, and the finished frame is blitted **1:1**. An optional reduced scale
  draws into a smaller offscreen target and upscales once; that path is off by
  default because the CPU copy costs more than it saves here;
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
                   (dimensions in `world_overlay/metrics.py`, bars in
                   `world_overlay/bars.py`, menus in `metrics.py`)

data/gameplay/     Tracked JSON gameplay values
assets/            TMX levels and sprites — required at runtime
docs/              Audit reports, measurements, open points, design proposals
```
