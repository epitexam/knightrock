# Benchmarks

There is no always-on frame readout: it used to run on every frame of every
session just to paint two lines in the corner, which made it noise the rest of the
time. Under `DEBUG=1`, the `PERFORMANCE` panel carries what is still worth reading
— frame rate, frame time, overlay and panel cost, sprite counts, text cache.

## Which script answers what

| Script | Question |
|---|---|
| `ui_benchmark.py` | How expensive is the interface text and cache path? |
| `fx_benchmark.py` | What does one particle cost to build? |
| `render_benchmark.py` | What does a presented frame cost, and what does the tile cull save? |
| `contact_benchmark.py` | Does the spatial index pay for itself at 1v1, 4v4 and 8v8? |
| `combat_feel.py` | How does combat actually play: swings per second, kill times, dodge windows? |
| `native_benchmark.py` | Does the optional mypyc build compute the same world, faster? |

```bash
uv run python tests/benchmarks/ui_benchmark.py
uv run python tests/benchmarks/fx_benchmark.py
uv run python tests/benchmarks/render_benchmark.py
uv run python tests/benchmarks/contact_benchmark.py
uv run python tests/benchmarks/combat_feel.py      # how the combat plays
uv run python tests/benchmarks/native_benchmark.py # after tools/build_native.py
```

> **Interpreting numbers.** These are medians from short, unprofiled runs on the
> development machine. Ratios between rows are meaningful; absolute milliseconds
> are noisy. The mypyc A/B alternates the order of its two modes and refuses to
> report a speedup unless the checksums agree.

Full measurements, including the Phase E results, are in
[the performance audit](audit/performance-2026-11.md).

## See also

- [Debugging](debugging.md) — the in-game diagnostics these scripts replace.
- [Architecture and rendering](architecture.md) — the pipeline being measured.
