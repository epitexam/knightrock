# Conventions

[Documentation index](../README.md) - [Development](../guides/development.md) - [Repository layout](repository-layout.md)

The conventions below explain the choices that are hardest to see from a single file.

- **Typed code.** `mypy src main.py tools` is blocking
  (`disallow_untyped_defs = true`, `disallow_incomplete_defs = true`) with **no
  per-module override left** in `pyproject.toml`. `tests/` is excluded, on
  purpose.
- **Formatted & measured.** `ruff format` for style, `C901` for cyclomatic
  complexity (threshold 10, every exception justified).
- **Deterministic simulation.** Fixed timestep
  (`Simulation.TICK_RATE = 60`). Nothing may introduce non-determinism into the
  tick.
- **Centralized tuning.** Gameplay constants live in `src/core/settings.py` — no
  magic numbers in the systems. A constant **shared by two modules has exactly
  one home**, and it belongs to the module that acts on it: HP-bar geometry is
  defined once in `src/ui/world_overlay/metrics.py`, which every layer that draws
  a bar reads, and it reaches the renderer through the `WorldOverlay` port rather
  than by `core` importing `ui`. Two copies agree only until someone edits one.
  UI-only constants (`HUD_PIP_SIZE`, `HEALTH_BAR_*`) stay in their UI module, and
  renderer internals (`DASH_STRETCH_*`) stay next to their only user.
- **One table for the interface.** `src/ui/metrics.py` holds every layout
  dimension of the menus as a `DESIGN_*` constant, and `Metrics` is the only
  thing that multiplies one by a scale. A view may not contain a layout literal.
  The reason is not tidiness: at a window density of 1.889 the grid used to pair a
  49 px font with 34 px rows, so a clickable band covered 44 % of the label above
  it and clicking the row you read activated the row above.
- **A row is never shorter than its text**, at any scale, in any window. A list
  that does not fit gives up *font size* (down to `MIN_TEXT_RATIO`) instead,
  because smaller text is still readable while an overlapping row is not clickable
  at all. `GridView` measures the real fonts rather than trusting the design
  constants, since a fallback face has different metrics again.
- **No dead menu options.** User-facing hotkeys are mirrored by tests.
- **Comments say why, commits say how it got here.** A docstring states what the
  code does and why the rule exists; a body comment explains an invariant or a
  choice that is not obvious. The history -- what it used to do, a measurement
  from one session, an audit identifier -- goes in the commit message or in
  `docs/`, where it cannot go stale next to code that has moved on.
- **Stand-ins have the real shape.** A test double for a fighter starts from
  `tests/fakes.py` (`BodyStub`, `FighterSprite`, `player_shape`, `game_shape`),
  which is pinned to the protocols it imitates. Production code does not read a
  declared field through `getattr(x, name, default)` to tolerate a partial fake.

## See also

- [Architecture overview](../architecture/overview.md) - the pipeline these rules protect.
- [Tests and quality](../guides/testing.md) - the gates that keep the conventions true.
