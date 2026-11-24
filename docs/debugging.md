# Debugging

> **The flag matters.** Everything below is inert unless the game runs with
> `DEBUG=1` (or `--debug`). Pressing an F-key without the flag shows a transitory
> notice naming it once, then stops: a key that silently does nothing is
> indistinguishable from a bug, but the flag is never implied either.

## Test bench

Every showcase feature is reachable from a single hotkey, live in game.

| Key | Feature | Detail |
|:---:|---|---|
| `1` `2` | Slash finishers | `slash_high_4`, `slash_low_4` |
| `3` `4` | Beat finishers | `punch_3` (uppercut, launches), `kick_2` (roundhouse, into the wall) |
| `5` | Charged slash | `charged_slash` — breaks a guard |
| `6` | Stab | `stab` — kills a downed foe |
| `7` `8` | Finishing moves | `death_blow`, `throw` — kill a helpless foe |
| `9` `0` | Air kit | `air_slash`, `air_kick` — **in the air only** |
| `V` | Projectile | plain `firebolt`, reuses `HitResolver` |
| `B` | Piercing projectile | passes through, hits each target once |
| `C` | Juggle dummy | pops an airborne dummy in front of the player |
| `G` `P` `T` | Spawn | goblin · slime · dummy |

<details>
<summary><b>Suggested juggle protocol</b></summary>

Press `C` to pop an airborne dummy, slash it in the air with `A` during the
jump, then `6` -- the stab -- once it lands.

Under `DEBUG=1` the overlay shows the offensive boxes plus `Combo (air xN)`,
`Juggle`, `OTG guard` and the `Shots` counter in the SCENE panel.

</details>

## Debug overlay

| Key | Layer / tool |
|:---:|---|
| `F1` | Hitboxes |
| `F2` | Labels |
| `F3` | Velocity arrows |
| `F4` | Static geometry — **off by default** |
| `F5` | Panels |
| `F6` | Freeze the simulation |
| `F7` | Step one tick (while frozen) |
| `F8` | Replay an attack |
| `F9` | Export it |
| `F10` | Next debug panel |
| `F11` | Panel layout — compact / full |

The full list is recalled on screen by the `DEBUG KEYS` panel.

### What the overlay draws

- **Hitboxes** — blue (player), red (enemy), grey (neutral), with a green hurtbox
  and an orange offensive box on top.
- **Velocity arrows** — tapered shaft, filled head, pivot dot, dark rim so the
  shape survives a bright sky. Head length is clamped and short vectors are
  stretched, so walks and dashes stay legible. Red while a hit is fresh or
  knockback still carries the entity, gold on a parry, yellow for locomotion.
- **Outlines** — cyan for OTG guard, purple for juggle gravity.
- **Labels** — short cards, with a second line only during an attack or when a
  flag is set. Projectiles show speed, lifetime and pierce; tiles are skipped.
- **Multi-box indices** — in-situ vector points, first filled, the rest hollow.

> **Everything is scaled by the density of the world it annotates**
> (`WorldOverlayMetrics`). An unscaled 1 px outline would arrive at 53 % of its
> intent at density 1.889 — a debug layer too thin to see is not a debug layer.

Culling is `Camera.is_visible`, the renderer's one world-space cull. Melee,
projectile AABB and moving-hazard geometry use **swept** collision; static
hazards and contact damage stay **discrete**.

> **Why `F4` ships off.** A level carries 839 terrain tiles whose outline tells
> you nothing, and drawing them is the most expensive thing the overlay does.
> Measured on level 0 at 1280×720, dropping the layer took the whole overlay pass
> from **1.98 ms to 0.09 ms** — 1.9 ms of a 16.7 ms budget, for a picture of the
> tileset.

## See also

- [Benchmarks](benchmarks.md) — the standalone measurements behind these numbers.
- [Architecture and rendering](architecture.md) — what the overlay is describing.
