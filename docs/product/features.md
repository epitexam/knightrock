# Features

[Documentation index](../README.md) - [Controls](controls.md) - [Gameplay data](gameplay-data.md)

Knightrock is a 2D hack 'n' slash platformer built with pygame-ce. It is designed around frame-data combat, a deterministic simulation, values that live in tracked data files, and an in-game diagnostic bench.

## At a glance

| Capability | What it does |
|---|---|
| Hack 'n' slash combat | High and low slashes and guards, a rechargeable blade battery, beats, throws, death blows on a direction prompt, a slot machine and a fury gauge that opens the dark side. Frame data has startup, active and recovery phases, plus multi-hitbox attacks. |
| Deterministic physics | Fixed 60 Hz simulation, sub-stepped swept collisions, moving and one-way platforms, spatial hashing. |
| Data-driven values | Attacks, enemies, the player and the level registry live in tracked JSON under `data/gameplay/`. |
| Scene stack | Menu, level select, options, video, controls, gameplay, pause, game-over and victory scenes over a synchronous, ordered event bus. |
| Interface sounds | One bus owns `pygame.mixer` and answers facts from the event bus (navigate, confirm, back). No screen names a cue or a file; silent and non-fatal without a sound card. |
| Debug test bench | Hotkeys to spawn foes, fire pooled projectiles and force showcase attacks, without recompiling. |
| Quality gates | Thousands of tests, strict mypy and Ruff, all blocking in CI. See [Tests and quality](../guides/testing.md). |

## Combat in one paragraph

Three attack buttons - blade, body and shot - throw high or low moves that can be charged. A killing slash leaves a foe doomed for a direction prompt; beats fill a stun gauge that opens a throw; two blades that meet enter a clash. Battery, fury, guard, dark step and the slot machine are tuned in `src/core/settings.py` and described in [Controls](controls.md).

## Where things live

- [Controls and options](controls.md): every binding, the combat loop and the options screens.
- [Gameplay data](gameplay-data.md): the tracked JSON files and how they load.
- [Architecture overview](../architecture/overview.md): how a frame is simulated and presented.
- [Debugging](../guides/debugging.md): the `DEBUG=1` bench and overlay.

## Historical material

Design proposals, playtest notes and audits are preserved in their original form under `docs/`. See the [history index](../audit/README.md).
