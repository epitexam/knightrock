# Benchmarks

## Frame timings & benchmarks

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
uv run python tests/benchmarks/native_benchmark.py # mypyc A/B (after tools/build_native.py)
```

---
