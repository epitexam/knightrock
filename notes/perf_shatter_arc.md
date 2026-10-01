# Performance pass: the shield-break arc

Measured 2026-09-30, after the dust rework. Every figure here is a median of
unprofiled runs, per the rule in `audit_p1_measured.md`: profiling charges a
Python-level call far more than it costs, and every line the FX plane draws with
is one, so a cProfile of this code is the wrong instrument.

Reproduce: `uv run python tests/benchmarks/fx_benchmark.py`.

## The frame is not slow

| window | density | world draw | present | frame | % of 16.7 ms |
|---|---|---|---|---|---|
| 1280x720 | 1.111 | 1.23 ms | 0.38 ms | **1.61 ms** | **10 %** |
| 1920x1080 | 1.667 | 1.38 ms | 0.61 ms | 1.99 ms | 12 % |
| 2560x1440 | 2.222 | 2.47 ms | 1.33 ms | 3.80 ms | 23 % |
| 3840x2160 | 3.333 | 6.06 ms | 2.80 ms | 8.86 ms | 53 % |

`Level.update` is 0.39 ms a tick. There is no frame problem at 720p, and an
optimisation aimed at "make the game faster today" is aimed at 90 % headroom.
The dust plane is 0.3 us a frame for 19 live particles: the ladders work.

## What was found

`ShatterArcParticle` built **1.14 ms of pixels at construction** and lived 300 ms.

```
ShatterArcParticle   1139.3 us   <- 6.9 % of a 60 Hz frame, on one tick
ShieldArcParticle      90.9 us
a whole landing dust  192.9 us
19 particles, one tick   0.3 us
```

One guard break cost sixteen times a whole landing, and it was the only
operation in the project close to a limit. Six times a second in a parry chain,
that is a hitch and not a cost.

The cause was 81 `draw_arc_stroke` calls per particle — 3 steps x (18 fragments
+ 9 kick pieces) — each sampling every **0.5 degrees** unconditionally, with two
`math.radians`, two trig calls and two `snap`s per sample in interpreted Python.
155-189 us for a single 140-degree arc at r=18.

And it could not be memoised **because of one line**: `spawn_shatter_arc` seeded
each break from `_fx_rng.randrange(1 << 16)`, so `_shatter` (now `_shatter_step`) was a pure function
keyed on a 65 536-wide space and 81 arc strokes were painted fresh on every
single break.

## What changed

The seed is folded into a grid of `FxGuard.SHARD_SEEDS` (8), the geometry moved
out of the constructor into `_shard_step`, and the particle steps a ladder keyed
on `(side, layout)` like the dust ladders.

```
first break of a layout (cold)   1208.4 us
every break once the table is up    1.9 us
```

**600x on every break after the first of each layout.** The table is bounded at
`2 sides x 8 layouts` = 16 entries, 48 surfaces, for the session, cleared by
`clear_frame_cache()` on a display-format change.

### What it did not fix

A cold layout still costs 1.2 ms, and there are 16 of them per session. So a
first-ever break on a side still hitches exactly as it did before; it happens 16
times in a session instead of every single break. The session's worst case is
~19 ms of extra painting spread over the whole thing, against ~6.8 ms a second
in the old code at six breaks per second.

The lever for the remainder is `SHARD_SEEDS` (lower = less variety, less cold
cost), and the better lever is the sample step below.

## Not done, and why

**`draw_arc_stroke` samples finer than the pixel grid.** One pixel of arc is
`360 / (2*pi*r)`: 3.18 deg at r=18, 9.55 deg at r=6. A flat 0.5 deg step is
finer than the grid by 6x at the guard ring's radius and 19x at a small one.
`fx_benchmark.py` reports the ratio per radius.

Measured against a radius-aware step, pixel-identical or not:

| radius | span | 1 px of arc | step tried | verdict | samples | us |
|---|---|---|---|---|---|---|
| 18 | 140 | 3.18 d | 1.06 d | **DIFFERS** | 281 -> 132 | 182 -> 90 |
| 18 | 40 | 3.18 d | 1.06 d | identical | 81 -> 38 | 58 -> 32 |
| 20 | 24 | 2.86 d | 0.95 d | **DIFFERS** | 49 -> 26 | 40 -> 26 |
| 14 | 18 | 4.09 d | 1.36 d | identical | 37 -> 14 | 30 -> 16 |
| 40 | 200 | 1.43 d | 0.50 d | identical | 401 -> 401 | 263 -> 226 |

A `1px / 3` rule is safe for the narrow spans the fragments use and breaks the
wide ones. **The bound is empirical and per span**, so it must be pinned by a
pixel-identity test over the radii and spans the plane uses, and the constant
moved until it passes — not taken from the table above. The current 0.5 deg
comment in `draw.py` says per-degree rounding merged the two ends of a fragment
(a real bug) and 0.5 was its fix; a radius-aware step has to keep fixing it, and
the test has to cover the *ends*, not the middle.

Deferred because after the ladder the arcs are painted 8 times per session
instead of once per break: ~7 ms per session, nothing.

**The magnification cache is unbounded.** `renderer._scaled_cache` has no
eviction and its value holds the source on purpose so `id()` cannot be recycled.
Verified: 500 distinct 16x16 surfaces scaled -> 500 entries, 500 more -> 1000.

Not a current leak — every `.image` assignment in `src/` is stable (animator
display cache, FX ladder rows, reused projectile surfaces), so it is bounded by
the asset set rather than by session length. Latent. `panel_renderer`'s
background cache is the correct pattern and is already in the codebase.

## Ruled out, with the numbers

Each of these is a plausible-sounding optimisation that measurement refutes.
They are here so the next pass does not spend a day on them.

| Hypothesis | Measured | Verdict |
|---|---|---|
| Pool the FX particles (`refacto.md` m3) | `Surface(3,3)` costs **0.39 us**; a whole `GrainParticle` is 9.6 us of which 2.4 is its surface | Wrong fix. The allocation is not the cost. |
| Put the FX plane back through the magnification cache | 19 live sheets on a landing are **19 distinct surfaces** — grains build their own and `tint` is continuous per grain — so there is nothing to share. `transform.scale` on them is 1-9 us, *less than the dict lookup a cache would cost* | Saves 0-4 us/frame. Measured 167.7 us either way. |
| Rebuild the physics timer dicts (`refacto.md` m6) | already measured by the project at 0.69 us, 0.3 % of the tick, explicitly reclassified as readability | Not a performance item. |
| The tile cull | `TileChunkIndex` is 0.06 ms flat from 1 000 to 22 000 tiles against 3.5 ms for the scan; worth 17-21 % of a 0.26 ms cull on the shipped level | Already done. |

And the dust specifically, since it was the change immediately before this: a
landing went from ~71 us to ~193 us when the grain family landed. **+120 us on
one frame, once per landing, 1.2 % of the frame budget**, against a 0.3 us
per-frame tick. Not worth optimising, and recorded because it was this pass's
own doing.

## Still open

**`find_landing_ahead`** (`entity.py:699-739`) is the one real O(n^2) left:
`steps x nearby` with a fresh `FRect` per outer step, up to four full spatial
queries and ~80 rect allocations per chasing enemy per tick, behind a fourth
spatial query in `is_at_ledge`. Never profiled in any note. Twelve enemies
against a 0.39 ms tick makes it invisible today; it only matters as the game
grows.

**4K headroom.** The frame is 53 % of budget at 3840x2160 and the step from
1080p to 1440p is non-linear (12 % -> 23 %), so something does not scale
cleanly past 1080p. The benchmark attributes it to fill and present, which is
resolution rather than code.
