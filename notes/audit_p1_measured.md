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
| P3.1 split the 2095-line `world_ui.py` | **done** -- four layers plus a 377-line orchestrator; see below |
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

### P3.1 — the overlay split, and why it is four modules and not three

`world_ui.py` is now a 377-line orchestrator, down from 2095. The four
extractions were planned against a call graph rather than against subject
matter, and the graph is what decided the shape:

| Module | Lines | Role |
|---|---|---|
| `world_overlay_shared` | 227 | sprite facts, annotation placement, the per-frame sink |
| `world_overlay_geo` | 679 | the producer pass: boxes, zones, sweeps, the attack chip |
| `world_overlay_cards` | 618 | the consumer pass: one card per sprite, dodging the above |
| `world_overlay_velocity` | 196 | the vector, its speed floor, and the two predicates tinting it |
| `world_overlay_panels` | 179 | screen furniture: the COMBAT readout, the clash ring |
| `world_overlay_shapes` | 146 | the three advanced poses, and the dashed outline |
| `world_ui.WorldUI` | 368 | reset, walk the sprites, place the cards, stamp the ring |

Two of these are leaves that the audit named and that the first cut did not
separate: `velocity.py` and the pose painter. `geo` is still over the audit's
400-line ceiling at 679, and `cards` at 618, and the reason is the same in both
cases -- what is left is a *pass*, and a pass is one loop body. Getting under
400 means cutting `draw_boxes` and `place_label` in half, which is a change to
the functions rather than a move of them, and the golden exists to make such a
change provable rather than to make it unnecessary.

The split that was asked for -- labels, boxes, panels -- cannot be done in three
modules without a cycle, and the reason is one method. The attack header chip
*draws* itself while the box pass is running, which means the box pass asks the
label pass where the chip landed; and the chip, in turn, asks the box pass what
it is dodging. Two calls, two directions. The way out was to let the chip travel
with the boxes, which makes the offending call internal to one module and leaves
`shared -> geo -> cards` and `geo -> panels` as a strict DAG. The first plan
called for five modules and was wrong about three of them: two of the five came
out smaller than anything else in `src/ui`, and `world_overlay_boxes` differed
from the already-shipped `world_overlay_bars` by two letters.

**The safety net came first.** `test_world_overlay_golden.py` froze the
geometry -- bar rects, annotation rects, and the padded rect of every placed
card, in a five-sprite scene chosen for the branch each sprite forces -- before
anything moved. It is geometry only: a pixel checksum would be a stronger test
and a worse one, breaking on font hinting between two SDL builds and then being
regenerated without being read. Every rectangle in it is byte-identical to what
the pre-split code produced, and that is the claim this refactor rests on.

The net was checked by mutation rather than trusted. Six deliberate breakages
were run against it; five failed a test, and the sixth -- neutering
`dodge_annotation` -- passed the entire suite, which is how it was found to be
unreachable: the attack header is always placed clear of the only obstacle it is
ever handed. It was kept, as the documented contract of the placement rule, and
written a test for, which corrected two wrong assumptions about its top-edge
branch along the way.

**Three things the split found that nothing was looking for.** The `rect`
fallback in `debug_reference` -- the one that gives hazards, moving platforms
and exits a rectangle at all -- was covered by no test anywhere, and deleting it
left the suite green. `previous_bar_obstacles` was read by a test and never
written by one, so removing the write was also green; there is now a test that
walks an entity under the top of the screen, which flips its bar from above to
below, and checks the card still clears the ground the bar left. And
`test_combat_panel_only_collects_when_debug_is_enabled` was passing on the
metrics throttle rather than on the DEBUG guard it claimed to test.

**The split cost 7 % of the overlay pass, and a benchmark caught it.** Each
layer was handed the metrics through a callable, because `WorldUI.metrics` is a
property and a layer has to see the table *change* on a resize rather than hold
a copy. That made every read of `metrics` -- several per sprite, hundreds per
frame -- go through a property, then a lambda, then the property again. Measured
against the pre-split tree on a 96-entity frame, four paired trials each showed
the new tree 2 to 7 % slower, with the sign never flipping. `MetricsCache` in
`world_overlay_metrics` now owns the "rebuild when the scale moves" rule and is
passed to the three layers directly, so a read is one attribute access and the
rule lives in one place -- which is also the only way three layers cannot
disagree about when the table went stale. The trials are mixed again afterwards,
and the 840-tile case is slightly faster. Worth recording because the number was
only visible by measuring both trees, and the golden cannot see time at all.

**One thing this branch broke and did not notice.** `tests/benchmarks/
ui_benchmark.py` read `renderer.ui_manager`, which commit 162d951 removed when
it inverted the core-to-ui dependency. The benchmark holds no `test_` function,
so pytest collected nothing from it and it stayed broken for several commits
while the README pointed at it for frame timing. It is fixed, and
`test_benchmarks_runnable.py` now runs all three entry points -- which is the
guard whose absence let this sit.

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

---

## End of branch: measured, base versus this branch

Both trees, same process, same level, medians of unprofiled runs:

| | base | this branch | |
|---|---|---|---|
| world draw, 1280×720 | 1.600 ms | 1.434 ms | **−10 %** (P1 only; the P3 split is a move, not a change) |
| `Level.update` | 537.5 µs | 391.1 µs | **−27 %** |

The tick is where the work went, and almost all of it is P1.2: the hazard and
contact systems were rebuilding a frozen fourteen-field `HitProperties` per
producer per tick, for producers whose damage never changes.

## The gates

`ruff check` clean · `ruff format --check` clean (it was **red** on the base
branch) · `C901` clean · `mypy src main.py tools` clean on 165 files ·
**2003 passed, 4 skipped** · `src/ui` coverage: bars, metrics and shared at
100 %, facade 99 %, cards 96 %, panels 93 %, geo 74 %.

Those percentages are *not* comparable to the pre-split baseline, which could
only be measured in a worktree where seventeen unrelated tests failed on missing
level assets. What is comparable is the accounting: of the 1424 test functions
present when the extraction started, one is gone -- the manifest check, replaced
by a strictly stronger version -- and 22 were added, 21 of them covering
`world_overlay_shared`. No test was narrowed, and every changed assertion line
across the four steps was a receiver rename with a byte-identical right-hand
side.

`geo` at 74 % is the honest weak spot and it is not new: it is the swept-box and
velocity-preview drawing, which a debug overlay's suite has never exercised
end-to-end because those paths need a mid-swing state the fixtures do not build.

The suite grew from 1813 to 2003, and it grew for a reason: every fix here
came with a test that fails against the old code, which was checked rather
than assumed. `test_readme_claims.py` also re-collects the suite on every run
and fails if the README's test count is wrong, so the number quoted above
cannot go stale without the suite noticing.
