# Rendering pipeline

[Documentation index](../README.md) - [Architecture overview](overview.md) - [Combat and physics](combat-and-physics.md)

## Rendering model

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

**Drawing scale comes from the window, not the camera.** A world unit gets
`window / framing` pixels — 1.667 at 1920×1080, 0.694 at 800×600. Art is magnified
once at load; the camera has no zoom, only a density read off the target.

### Displays

- pygame-ce reports display **sizes** only. `src/core/display/sdl_probe.py` reads
  the bundled SDL2 through `ctypes` for each screen's bounds, usable area,
  platform name, refresh rate and compositor scale.
- The probe is cross-checked against pygame's numbers and discarded if they
  disagree: a second libSDL2 can answer plausibly while never initialised.
- Without the probe, the game falls back to what pygame can say.

```
pygame  SDL_GetDesktopSizes()          -> [(1920, 1080)]
SDL     SDL_GetDisplayBounds(0)        -> (0, 0, 1920, 1080)
SDL     SDL_GetDisplayUsableBounds(0)  -> (0, 32, 1920, 1048)
SDL     SDL_GetDisplayName(0)          -> b'eDP-1 17"'
```

### The window is the target

No display mode, exclusive fullscreen, borderless or screen picker. Three rules:

1. **Size is a request.** The window opens on the screen it last closed on (or the
   primary), at the player's chosen size or the largest that fits, then the player
   drags it. The screen is remembered by name; position belongs to the window
   manager.
2. **The target is the window's fitted rectangle** at scale 1.0; the frame is
   blitted 1:1. A reduced internal scale draws offscreen and upscales once — off
   by default here because the CPU copy costs more than it saves.
3. **Fit is a choice**: bars, whole-pixel blocks, or zoom with a crop. All show at
   most the framing; the HUD is laid out in the visible part (`Game.shown_area`).

Resizing rebuilds the target, re-reads density and re-lays out the interface: one
cascade shared with a window rebuild. **It never changes how much world is seen.**

- The size is **polled from the window**, not from an event: one SDL resize becomes
  seven pygame events and the carrier depends on platform and gesture.
- The frame in which the size changed re-lays out the interface **before** input
  is read. Without that, a click was converted through the new picture and tested
  against the old rectangles — measured 244 px off.
- `reset_cache` drops the rectangles for a change the game makes while handling
  input, with another input already queued.

The **VSync row** reports the screen the window is actually on, found from its
position. If it cannot be established the row says nothing. Display hot-plug is
polled on a timer; a window whose screen disappears is rebuilt on the primary.

<details>
<summary><b>Why size is a request and framing is not derived from the window</b></summary>

- A hardcoded size list claims things about a monitor the game cannot check
  (e.g. 2560×1440 on a 1366×768 laptop). Offered sizes are derived from the
  current panel and filtered to what it holds.
- A saved size is honoured where it fits and clamped where it does not; the file
  keeps what the player chose. The old `width`/`height` keys were overwritten at
  launch, so a size never survived a change of machine.
- The framing used to be built from window pixels and a zoom constant, making the
  visible world a video setting: the reveal ran from 34 % to 60 % of a level's
  height, and a large preset showed a whole 40×15 level. It is now fixed.

Two tests pin it:

- `tests/unit/test_framing_contract.py` — framing is smaller than every level;
- `tests/unit/test_sim_is_display_independent.py` — one input log, five window
  sizes and five densities, same world checksum.

</details>

<details>
<summary><b>Measured: 1:1 present vs <code>smoothscale</code></b></summary>

| Window | 1:1 | `smoothscale` |
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

### Draw planes

The world is drawn from three **planes**, split by one property: whether the
sprite moves.

| Group | Contents | Culling |
|---|---|---|
| `SpriteGroups.static_sprites` | Background and terrain layers, built once | `TileChunkIndex`, a chunk grid built at load |
| `SpriteGroups.all_sprites` | Everything that moves | Scanned — exact and cheap, tens of sprites |
| `SpriteGroups.fg_sprites` | Foreground tile layers | `TileChunkIndex` |

The split is what makes the index pay:

- Leaving tiles in `all_sprites` would make the renderer walk all 839 of them
  each frame just to discover they were already drawn.
- Measured on level 0: **0.22 ms indexed vs 0.28 ms scanned**; at 22 000 tiles,
  **0.07 ms vs 2.67 ms**.
- Tile layers stay in `collision_sprites`, so physics is untouched.

Anything that genuinely needs the whole world — the debug overlay, the sprite
counter — reads `SpriteGroups.every_sprite`. The index only decides which sprites
are *worth asking about*; `Camera.is_visible` still decides which are drawn, so a
chunk can over-select but never under-select.
