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

The conventions that shape these modules are collected in [Conventions](../reference/conventions.md).

## Further notes

The README and the guides under `docs/` are in English. The audit notes in
`docs/audit/`, the design proposals and the playtest write-ups are historical
records kept in their original form and language; see the
[history index](../audit/README.md).

| File | Contents |
|---|---|
| `docs/design/matrice-niveaux.md` | Proposal, not implemented: a world of rooms laid out as a matrix. |
| `docs/playtest-2026-11-18.md` | Combat-feel observations from November 2026. |
| `docs/pr-fix-hitbox-fluidity.md` | Reasoning behind the hitbox fluidity fix. |

## See also

- [Architecture and rendering](../architecture/overview.md) — the pipeline these modules
  implement.
- [Tests and quality](testing.md) — the gates that keep the conventions true.
