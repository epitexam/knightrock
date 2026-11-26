# Repository layout

[Documentation index](../README.md) - [Conventions](conventions.md)

The tree below is the one described in [Architecture overview](../architecture/overview.md). Generated files, caches and the virtual environment are not tracked.

```
src/
├── application/   Composition root (game.py), scene stack, save game, settings store
│   └── scenes/    menu · level select · options · video · controls category ·
│                  controls · gameplay · pause · game over · victory
├── combat/        Frame data, hit resolver, knockback, charge and combo
│                  tracking (CombatSystem lives in core/level/systems/)
├── core/          Event bus, settings, paths, colors, object pool,
│                  hazards, sprites, sprite groups, asset library, audio
│   ├── animation/ Animator
│   ├── display/   Framing, letterbox, Viewport, Stage, Presentation, monitors, detection, sdl_probe
│   ├── fx/        Draw, particles, spawners
│   ├── input/     Bindings, providers, managers, input state
│   ├── level/     Level facade + ordered fixed-tick systems
│   ├── rendering/ Camera (fixed framing + a density read off the target),
│   │              renderer, tile chunk index, world-overlay port
│   └── rollback/  Snapshot ring buffer and deterministic restore
├── data/          Strict JSON loaders + in-code fallback values
├── entities/      Entity base, player + controllers, projectiles, vitals,
│                  crouch posture
│   └── enemies/   Data-driven configs, factory, per-type behaviour
├── physics/       Collisions, gravity, movement, spatial hash, entity grid
├── states/        State machines (player, enemies, shared reactions, turn)
└── ui/            Player HUD, panels, world-space debug overlay
                   (dimensions in `world_overlay/metrics.py`, bars in
                   `world_overlay/bars.py`, menus in `metrics.py`)

data/gameplay/     Tracked JSON gameplay values
assets/            TMX levels and sprites — required at runtime
docs/              Audit reports, measurements, open points, design proposals
```

## Reading the tree

- `src/application/` is the composition root: it is where the interface and the simulation are allowed to meet.
- `src/presentation/` owns framing and rendering; `src/platform/` owns input and audio; `src/shared/` owns events and the ports. None of them is imported by `src/simulation/`.
- `src/simulation/level/systems/` holds the ordered fixed-tick systems, including combat.
- `data/gameplay/` is tracked JSON; see [Gameplay data](../product/gameplay-data.md).
- `assets/` holds TMX levels and sprites required at runtime.
- `tests/` is deliberately excluded from mypy; see [Tests and quality](../guides/testing.md).
- `docs/audit/` and the historical notes are preserved as written; see the [history index](../audit/README.md).
