# Development

Start with the [module map](#reading-the-code-module-by-module) if you are new to
the tree. The conventions below explain the choices that are hardest to see from
a single file.

## Reading the code, module by module

| Module | Owns |
|---|---|
| `src/application/game.py` | The display, the input and the scene stack. The loop feeds fixed ticks to the active scene, draws into the render target and presents it once. |
| `src/core/level/systems/gameplay_loop.py` | The *order* in which the level systems run. `GameplayLoop` requires every stage, so a loop that exists can run a tick; `CombatLoop` is the combat core alone, for tests. |
| `src/core/events.py` | A synchronous, strictly ordered event bus with two families of facts: simulation milestones (`LevelStarted`, `PlayerDied`, `LevelCompleted`, emitted from the fixed tick by a `Level` that holds no reference to the application) and interface feedback (`UiFeedback`, emitted by the input dispatcher from what a screen reports). Subscribers must never mutate the simulation. |
| `src/core/audio.py` | The only module that touches `pygame.mixer`, and it is a **consumer**: it never asks who did something and imports neither the input router, the menu model, the scenes nor the views. `cue_for(effect)` is the whole policy — one effect, one cue — and `attach(bus)` subscribes to the facts it answers. It loads each sound once, caches it, applies the cue's category volume and never raises: no sound card, no asset and an undecodable file all end with a warning and a silent cue, which is also the CI path. |
| `src/core/rendering/overlay.py` | The `WorldOverlay` port. `UIManager` implements it and `Game.world_overlay` builds it once. |

**The frame loop is paced exactly once.**

- Vsync off — the `Clock` holds the frame limit.
- Vsync on — the present already blocks on the vertical blank, so the clock is
  ticked only against a runaway ceiling derived from that rate. Targeting 60 on a
  60 Hz present would wait twice for one refresh and alternate between on time
  and one refresh late.
- The ceiling is a backstop, not a frame-rate control. It is derived, not
  hardcoded, so raising the limit can never leave it underneath.
- `Display.FPS` is a build target feeding that ceiling — **not** the player-facing
  frame rate, which lives in `settings_store.FRAME_LIMITS`.
- A frame runs at most `Simulation.MAX_TICKS_PER_FRAME` ticks; the surplus is
  dropped.

> **The interface reaches the world by injection, not by import.** The renderer
> takes a `WorldOverlay` and draws nothing beyond the world without one, so `core`
> never imports `ui`. `GameplayScene` does name `UIManager` concretely, which is
> the point: `application` is where the two layers are allowed to meet.
> `tests/unit/test_layer_boundaries.py` enforces the direction, so the next
> convenient import does not put it back.


## Conventions

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


## Further notes

The README and the guides in `docs/` are in English. The audit notes in
`docs/audit/`, the design proposals and the playtest write-ups are in French.

| File | Contents |
|---|---|
| `docs/design/matrice-niveaux.md` | Proposal, not implemented: a world of rooms laid out as a matrix. |

## See also

- [Architecture and rendering](architecture.md) — the pipeline these modules
  implement.
- [Tests and quality](testing.md) — the gates that keep the conventions true.
