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

---

## P2 and P3: what was done, and what was not

The audit's architecture phase is a mix of real defects and items that were
already correct or already done. Recorded here so the next reader does not
re-open the closed ones.

| Item | Verdict |
|---|---|
| P2.1 scene hooks found by `getattr` | **fixed** -- declared on `Scene`, plus a `ScaledView` Protocol |
| P2.2 `game: Any` chain | **fixed**, at the size the code supports (one member, not six) |
| P2.3 `core` → `ui` inversion | **fixed** -- `WorldOverlay` injected, boundary test added |
| P2.4 event subscriber isolation | **fixed** -- a raising subscriber no longer kills the tick |
| P2.5 fatal error path | **fixed** -- traceback logged, target painted, never raises |
| P2.6 duplicated cell size, late injection | **fixed** -- one constant, spawner wired once |
| P2.7 split the 1106-line `Entity` | **already done** -- see below |
| P3.1 split the 2095-line `world_ui.py` | **partly** -- dimensions moved, drawing not split |
| P3.2 `Level`'s delegating properties | **one name, not six** -- the rest is the deliberate facade |
| P3.3 dead sprite type check | **removed** |
| P3.4 `DISPLAY_SAFETY_CEILING_FPS = 720` | **already correct** -- see below |
| P3.5 `SpatialHash` `id()` key | **fixed** -- key made checkable, death unregisters |
| P3.6 187 `Any`, 333 `getattr` | **declined**, with one docstring corrected |

### P2.7 — `Entity` was already a composition root

The audit proposed extracting `EntityKinematics`, `EntityVitalsAdapter` and
`EntitySweep`. `MovementComponent`, `Vitals`, `ReactionComponent` and
`CombatComponent` already own that state; the twelve properties on `Entity`
forward to them and hold nothing.

They are not incidental. `entity.velocity` has 223 external call sites and
`entity.on_surface` has 98, most mutating in place from `src.physics` and the
state machine — which is exactly why the getters return the component's live
object rather than a copy. "Extracting the adapters" means mixins, which buy
nothing over the properties already there, or wrappers, which break the 223
call sites for no gain.

`tests/unit/test_entity_composition.py` guards the finding against the
*opposite* regression: inlining the state back into `Entity` would pass every
behavioural test in the suite while re-creating the coupling the components
removed.

### P3.4 — the frame ceiling was never the frame rate

`DISPLAY_SAFETY_CEILING_FPS` is 720 because it is
`max(Display.FPS * 4, MAX_FRAME_LIMIT)`, and the audit read 720 as "lets the
game run at 720 without vsync". It does not. With vsync off,
`clock.tick()` is called with **the player's own frame limit**; the ceiling is
only used with vsync on, where the present is the pacer and a 720 fps tick can
never bite (`test_frame_pacing.py` asserts exactly this). Three tests already
covered it. Nothing changed.

### P3.6 — the `Any` and `getattr` counts are the seam, not a pass-through

183 `Any` annotations and 361 `getattr` calls, against the audit's 187 and 333
— so the drift is real but the totals were close. What the audit did not
separate is that most of them are *deliberate and correct*:

- `world_ui.py` alone has 115 `getattr`. The debug overlay must accept a
  plain `Sprite` (a terrain tile), an `Entity`, a `Projectile` and a
  `Hazard`, and read attributes that only some of them have. Typing it
  against a Protocol would mean the overlay could no longer be handed a tile.
- The state machines take a loose owner protocol for the same reason.

The one instance the audit named — `contact_system` declaring
`swept_hurtbox` on `Combatant` *and* doing a `getattr` — is not redundancy
either, and that is now written down where the next reader will see it: the
fallback is behaviour. A target with no previous-tick capture has no swept
geometry, and the discrete hurtbox is then the best available answer rather
than a wrong one. The protocol says what a combatant *is*; the `getattr` says
what to do when it cannot answer.

The general advice — "reduce `Any` by using the `Protocol`s already declared
rather than `getattr`" — would, applied to the overlay or the state machines,
make the code *worse*: the flexibility is the feature. What is worth doing is
what this branch did: fix the places where `Any` was a genuine pass-through
(`Level.draw`'s `game`, the renderer's `UIManager`) and leave the seams
alone.
