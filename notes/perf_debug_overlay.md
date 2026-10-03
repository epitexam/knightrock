# Performance pass: the debug overlay

Measured 2026-10-03, after the panel-scale work. Same rule as
`perf_shatter_arc.md`: every figure is a median of unprofiled runs, because
profiling charges a Python-level call far more than it costs, and the overlay is
almost entirely such calls.

**Nothing was changed.** This note is the record of why, since the reasoning is
not visible in the code, and the next person to read `world_ui.py` and see four
obvious inefficiencies will reasonably assume nobody looked.

Reproduce the headline:

```
uv run python tests/benchmarks/ui_benchmark.py
```

## The overlay is not a cost

The full player stack at 1280x720, every panel drawn, `DEBUG=1`:

```
full player panel stack : 0.123 ms   (0.74 % of a 60 Hz frame)
```

0.74 % of a 16.7 ms budget. There is no frame problem here and no optimisation
that would pay for itself. For reference the same script measures the whole frame
at 1.61 ms at 720p (`perf_shatter_arc.md`) -- the overlay is under a tenth of the
frame, and the frame is under a tenth of the budget.

The menu is likewise flat: `VideoScene` 0.20 ms p50, `MenuScene` 0.30 ms p50, and
both *fall* as the window grows, because they draw a fixed number of rows rather
than scaling with the window.

## What was found, and what it actually costs

### The `statics` layer: 1.9 ms, and off by default

The one finding that is genuinely large. A level carries ~840 terrain tiles whose
outline tells you nothing, and outlining them is the most expensive thing the
overlay does -- measured on level 0 at 1280x720, the whole overlay pass goes from
1.98 ms to 0.09 ms with the layer off. That is **11 % of a 60 Hz frame for a
picture of the tileset**.

It starts off (`world_ui.py`), and F4 brings it back. That is the right default and
the right amount of work: the layer exists, it is one keypress away, and paying
1.9 ms for it only when asked beats paying it never. Nothing to do.

### The label dodge is O(n^2) -- in labels, not entities

`world_overlay_cards.py:442` tests each candidate card against every card already
placed, so cost grows with the square of the label count. Measured, worst case
(heavy overlap, so nothing is accepted early and the scan never short-circuits):

| labels | dodge pass | per label |
|---|---|---|
| 10 | 0.0046 ms | 0.46 us |
| 20 | 0.0106 ms | 0.53 us |
| 40 | 0.0346 ms | 0.87 us |
| 80 | 0.1053 ms | 1.32 us |

Clean quadratic, and it stays the right shape for one reason: the count is
*labels*, not entities or colliders. A level with 972 candidate colliders draws a
handful of cards, because a card needs a labelled sprite with an anchor. Reaching
80 labels means 80 simultaneously-labelled combatants, at which point 0.105 ms is
0.6 % of a frame and the quadratic is not the thing costing frames.

A spatial hash would make it linear, and is the same shape as the `_headroom` fix
already in `Level.update`. It would be a change to a working dodge routine for no
measurable gain, so it is written down instead of written.

### Two string tables and a history copy, in microseconds

`PlayerUI._state_lines` rebuilds its seven f-strings every frame, and
`list(state_machine.history)[-6:]` copies the history to take six of them:

```
_state_lines (state panel) : 0.0038 ms
  of which the history copy: 0.0001 ms
```

3.8 us out of a 16,700 us frame. The lines *have* to be rebuilt -- every one holds
a live value -- so the only saving available is the 0.1 us copy, which is not a
change worth a test.

### Metrics are already throttled

`update_metrics` reads three counters and rebuilds its text every frame unless
`METRICS_TICK_DIVISOR` (10) divides the tick -- so the string work happens on one
frame in ten. Worth recording because it reads as an oversight on a first pass: it
is not, and the divisor is right there.

## The duplication that is not worth removing

Three things are computed twice per frame, and all three are cheap:

- `health_bar_rect` is called from both `draw_labels` and `label_clearances`.
- `render_text` runs twice over the same panel text during a fit pass.
- `status_flags` is read twice by the KEYS panel.

Each would become a cache with an invalidation rule, and each cache is a new way
for the overlay to show a value from the previous frame -- the exact bug class the
liveness split in `3b58f82` existed to remove. At microsecond cost the honest
trade is the duplicate call, not the stale cache.

## Why nothing was optimised

An optimisation here would have to beat 0.74 % of the budget to matter, and the
three items above total under 4 us between them -- 0.02 %. The real cost in this
overlay is the `statics` layer, and that is already off unless asked for.

The one thing worth doing was the thing already done: make the panels fit, so the
overlay can be read on a window too small for it at 1.0. That is `ac94090`, and it
is a legibility fix, not a performance one.