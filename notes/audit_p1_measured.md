# Audit P1 performance: what the numbers actually say

> Recorded 2026-09-27 on branch `refactor/audit-refacto`, applied from
> `refacto.md`. This file exists because the audit's performance figures did
> not survive contact with a measurement, and a reader who takes them at
> face value will re-litigate decisions that were made on better data.

## The method problem, first

`refacto.md` reports its profile with **cProfile**. Profiling charges a
Python-level call far more than it costs, and the lines it identified as hot
are precisely the ones made of hundreds of small calls per frame. The same
profile puts the whole world draw at **2.8 ms/frame**; measured unprofiled it
is **1.22 ms**. Every figure in the audit's §1 is inflated by roughly that
factor, and the ratios between them are distorted too, because a cull loop
and a `pygame.draw` call do not inflate by the same amount.

So the rule adopted for this branch: **no performance claim is accepted or
rejected from a profile.** Medians of unprofiled runs, and a benchmark that
can be re-run to check the number.

## Per-item verdicts

| Audit item | Audit claim | Measured | Verdict |
|---|---|---|---|
| P1.1 terrain cull | −1.4 ms/frame | −0.085 ms (−7 % of the draw) | kept, on different grounds |
| P1.2 hazard/contact boxes | −0.4 ms/tick | **−0.14 ms/tick (−25 % of the tick)** | the real win |
| P1.3 `EntityGrid` threshold | −0.3 ms/tick | −0.026 ms/tick (−6 %) | kept |
| P1.4 asset fallback | 39 µs → 0.1 µs | **35.7 µs → 0.23 µs** | confirmed, as measured |
| P1.5 FX surface pooling | ~60 `Surface`/s | 0.17 µs/particle/frame, and pooling is the wrong fix | mostly declined, see below |
| P1.6 physics timer dicts | −0.15 ms/tick | 0.3 % of the tick | **not done** |

### P1.1 — kept, but not for the reason given

The audit's premise is right and its number is wrong. 840 tiles are
camera-culled per frame to find the ~115 that are visible, and the terrain
never moves. But a *culled* sprite is cheap — one `Sprite.rect` and one
C-level `colliderect` — so on this level the whole cull is 0.28 ms of a
1.2 ms frame, and eliminating 85 % of it saves 0.003 ms.

The index is in the renderer anyway, because the shape of the cost is what
matters and it is now measured rather than assumed:

| tiles | linear scan | chunk index |
|---|---|---|
| 839 (the shipped level) | 0.275 ms | 0.220 ms |
| 1 000 | 0.170 ms | 0.057 ms |
| 4 000 | 0.526 ms | 0.059 ms |
| 22 000 | 2.673 ms | 0.073 ms |

The scan is linear in the level; the index is flat. The shipped level sits
almost exactly on the crossover, which is why a single measurement cannot
decide this and only a curve can. `render_benchmark.py` prints both tables.

**`CHUNK_TILES` is 4, not the audit's 16.** At 16 tiles a chunk is 1024 world
units against a 1152×648 framing, so a single query returned two thirds of
the terrain and the index was *slower than no index at all*. That was
measured, not reasoned: the first implementation used 16 and had to be
changed.

### P1.2 — the actual headline

`HitProperties` is a frozen dataclass of fourteen fields with a validating
`__post_init__`, and it measured **2.9 µs to construct**. The hazard and
contact systems built one per producer per tick, for producers whose damage
and knockback never change. On the registered level that is 35 hazards ×
2.9 µs = 103 µs of a 562 µs tick, producing objects identical to the ones
the previous tick had discarded.

Caching them took `Level.update` from **561.9 µs to 421.7 µs**. That is five
times the entire P1.1 saving, and it is the only item in the audit's
performance phase that moved the tick by a double-digit percentage.

### P1.5 — declined as proposed, one part taken

The audit proposed pooling particle surfaces to stop "~60 `Surface`/s of GC
churn". The cost is not the allocation; it is the `pygame.draw` calls inside
`_render`. A pool would have left the cost where it was.

Of the four particle types that redraw per frame, three genuinely have new
pixels (a rotating vortex, an expanding ring, a framed strip cycling) and
one — `DashTrailParticle` — was rebuilding a byte-identical image, which is
fixed and is now built once. `fx.py` now documents which is which.

### P1.6 — not done

Three `id(entity)`-keyed dicts rebuilt per tick, and a `hasattr` per entity
per tick. Measured: `_cleanup_timers` is **0.69 µs** and the whole
`_spawn_impact_fx` pass is **2.31 µs**, against a 394 µs tick. That is 0.3 %,
below the run-to-run noise of the measurement, and the change would have
made the code harder to read to recover a rounding error.

It stays on the list as a *readability* item, not a performance one: the
`hasattr(entity, "landed_impact")` probe would read better as a protocol
check, and if it is ever done it should be done for that reason and labelled
as such.

## What the frame actually costs

For anyone coming back to this: on the registered level at 1280×720, the
1.2 ms world draw is **0.19 ms filling the target, 0.45 ms blitting the ~115
visible tiles, and 0.28 ms deciding what to blit**. Only the last of those
is affected by level size, and it is the smallest. The frame is not
culling-bound and was never going to be.
