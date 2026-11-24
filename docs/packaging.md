# Packaging & releases

The game ships as a standalone PyInstaller bundle driven by `knightrock.spec`
(it embeds `assets/` and `data/`):

```bash
uv run --with pyinstaller==6.22.2 pyinstaller knightrock.spec --noconfirm --clean
```

An optional, development-only native build compiles five physics helpers with mypyc:

```bash
uv run python tools/build_native.py            # install .so files next to the sources
uv run python tools/benchmark_native.py        # A/B against the interpreted tree
uv run python tools/build_native.py --clean    # remove every generated artifact
```

The source files remain authoritative and the released bundles are pure Python; the
measured A/B and the reason for the narrow perimeter are in
`docs/audit/performance-2026-11.md`.

`.github/workflows/build.yml` then:

1. runs tests, lint, format and mypy on every push / pull request to `master`;
2. builds `knightrock-linux`, `knightrock-windows` and `knightrock-macos`
   artifacts, with a **headless smoke test** that boots the packaged binary;
3. publishes a GitHub Release with those artifacts when a `v*` tag is pushed.

## See also

- [Tests and quality](testing.md) — the gates the workflow runs before packaging.
- [Benchmarks](benchmarks.md) — the optional native build is measured here, not
  shipped in the bundle.
