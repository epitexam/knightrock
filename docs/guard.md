# Guard System

Player defensive system replacing the previous hold-to-block stamina pool.

## Concepts

- **Directional frontal guard.** Hits only count as guarded when the source
  is in front of the player (`Player._faces_source`). Hits from behind deal
  full damage and interrupt normally.
- **Mobile guard.** Guarding slows horizontal movement (`Guard.MOVE_MULT`)
  instead of rooting the player. Jump and dash cancels stay available through
  the shared interrupt table.
- **Chip damage.** Guarded hits deal `damage * Guard.CHIP_RATIO` HP damage.
  Guarding buys time and positioning, never full immunity.
- **Posture.** Each guarded hit costs `damage * Guard.POSTURE_COST_RATIO`
  posture (x`Guard.AIR_POSTURE_MULT` in the air). Posture regenerates at
  `Guard.REGEN_PER_S` while not guarding.
- **Parry.** Pressing guard arms `Guard.PARRY_WINDOW` seconds of parry.
  A hit taken inside the window deals no chip, costs no posture, applies no
  push, refills posture, and arms `Guard.RIPOSTE_WINDOW` for a punish.
- **Guard break.** Posture reaching zero breaks the guard: chip still
  applies, the player staggers for `Guard.BREAK_STAGGER`, and guard is locked
  for `Guard.BREAK_LOCKOUT`.

## Tuning (`src/core/settings.py`, class `Guard`)

| Field | Default | Meaning |
|---|---|---|
| `MAX_POSTURE` | 100.0 | Posture pool |
| `REGEN_PER_S` | 35.0 | Regen while not guarding |
| `CHIP_RATIO` | 0.15 | HP fraction passing through guard |
| `POSTURE_COST_RATIO` | 2.0 | Posture cost per damage point |
| `PARRY_WINDOW` | 0.15 | Parry timing after press (s) |
| `RIPOSTE_WINDOW` | 0.6 | Punish window after a parry (s) |
| `MOVE_MULT` | 0.35 | Movement speed factor while guarding |
| `AIR_POSTURE_MULT` | 1.5 | Posture cost factor in the air |
| `PUSH_FACTOR` | 0.15 | Knockback fraction kept on guard |
| `BREAK_LOCKOUT` | 1.2 | Guard lockout after a break (s) |
| `BREAK_STAGGER` | 1.0 | Stagger applied on break (s) |

Per-player overrides: `PlayerConfig.guard_posture_max`,
`PlayerConfig.guard_break_lockout` (JSON keys `guard_posture_max`,
`guard_break_lockout`).

## Code map
- `src/entities/player_controllers.py` — `GuardController` / `GuardSnapshot`
  (posture, lockout, parry, riposte; rollback-safe).
- `src/states/player_states.py` — `PlayerGuardState`, `PlayerState.GUARD`,
  `_can_guard` interrupt (priority 60, dash keeps 80).
- `src/entities/player.py` — `is_guarding`, `_faces_source`,
  `_apply_guard_reaction`, `receive_damage` guard branch.
- `src/combat/combatant_protocol.py` — `DamageResult(guarded, parried,
  guard_broken)`, `GuardingCombatant` protocol.
- `src/entities/components/reaction.py` — `ReactionKind.GUARDED/PARRIED`,
  `note_guard_push`.
- `src/core/input/` — `guard_held` + `guard_just_pressed` edge driving the
  parry window.
- `src/core/level/systems/combat_system.py`,
  `src/core/level/systems/projectile_system.py` — guarded contacts are
  consumed (no multi-dip) with hit-stop.

## Effects

Every guarded outcome is readable in-game without opening the debug panels:

| Outcome | Particles | Hit-stop | Camera | Overlay |
|---|---|---|---|---|
| Guard | 6 cyan chips | standard | light (`GUARD_TRAUMA`) | red push vector |
| Parry | 14 gold sparks, kicked upward | floored at `PARRY_HITSTOP` (0.14s) | medium (`PARRY_TRAUMA`) | gold vector + `RIPOSTE` line in the stats panel |
| Break | 12 red/orange shards | standard (chip hit) | heavy (`BREAK_TRAUMA`) | guard line turns critical + lockout timer |
| Stun | 12 gold orbiting stars | standard | heavy (`BREAK_TRAUMA`) | `DIZZY x.xxs` gold flag on enemy card |

How it flows: `CombatSystem` and `ProjectileSystem` record render-only
`GuardEvent(kind, target)` entries while resolving contacts; `GameplayLoop`
drains them once per tick, spawns the matching `fx` burst into
`fx_sprites`, and feeds the strongest trauma of the tick to the camera.
Particles never touch snapshots or golden digests; event lists reset every
tick, so rollback re-simulation regenerates them deterministically.

## Parry Stun (DIZZY)

Consecutive perfect parries build up a counter on the **attacker** (not the
player). When the counter reaches the enemy type's threshold, the attacker
enters the `DIZZY` state: frozen in place, vulnerable, taking `1.5x` damage
(`Combat.DIZZY_DAMAGE_MULT`), and marked with a gold `DIZZY` flag in the
world overlay. The counter is **consecutive** — it resets to zero whenever
the attacker lands a real HP hit on the player (chip damage through guard
does not reset it). Projectiles and dummy entities are excluded.

### Configuration (`src/entities/enemies/schema.py`, class `EnemyConfig`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `parry_stun_threshold` | `int \| None` | `None` | Consecutive parries needed to dizzy. `None` = immune. |
| `parry_stun_duration` | `float` | `0.0` | Seconds the dizzy state lasts. |

### Defaults (placeholders in `src/entities/enemies/types/*.py`)

| Enemy | Threshold | Duration |
|---|---|---|
| Goblin | 2 | 1.5 s |
| Slime | 3 | 2.0 s |
| Dummy | immune | 0 s |

### Per-player tracking

- `Entity.parries_given` — total perfect parries landed this life (saved in rollback).
- `Entity.parries_taken` — consecutive perfect parries received (reset on real hit).
- Both round-trip through `EntitySnapshot.extra` for determinism.

### Code map (additions)

- `src/states/reaction_states.py` — `DIZZY_STATE = "dizzy"`, `DizzyState` shared class.
- `src/states/enemy_states.py` — `EnemyState.DIZZY`, `EnemyDizzyState` (exits to `idle` on timer).
- `src/states/player_states.py` — `PlayerState.DIZZY`, `PlayerDizzyState` (exits via `ground_return`).
- `src/core/level/systems/combat_system.py` — increments `parries_taken`, triggers `DIZZY`, emits `GuardEvent("stun")`, resets counter on real hit.
- `src/combat/hit_resolver.py` — applies `DIZZY_DAMAGE_MULT` (1.5x) when target state is `dizzy`.
- `src/core/fx.py` — `spawn_dizzy_stars` (orbiting gold stars).
- `src/ui/world_ui.py` — `DIZZY x.xxs` gold flag in enemy label card.

## Dash System

The dash is a core mobility and combat tool with invincibility frames, directional flexibility, and deep combat integration.

### Core Mechanics

- **Invincibility frames** — `tags=["dash", "invincible"]` grants full phasing through enemies and projectiles (hit resolver, contact damage, separation all respect `is_invincible`).
- **Directional control** — Dash direction follows the input axis at press time (`DashController.request(move_axis)`), enabling reactive opposite dashes. Mid-dash direction changes use strong air control (`Physics.DASH_AIR_CONTROL = 3000`, 5x multiplier when reversing) for Brawlhalla-style zigzag.
- **Speed & duration** — `DASH_SPEED = 1100`, `DASH_DURATION = 0.08` (faster, punchier than legacy 800/0.12).
- **Charges & penalty** — 5 charges, 0.35s recharge, 2.0s penalty when fully drained (sweat FX).

### Combat Integration

| Feature | Window | Effect |
|---|---|---|
| **Cancel window** | `DASH_CANCEL_WINDOW = 0.0s` | Attack/guard may cancel a dash as soon as it starts. Non-zero values keep the dash committed for that long; note the 60 Hz granularity (interrupts run before the dash state decrements its timer, so a 0.04s window on a 0.08s dash only accepted a press on its last frame — measured). |
| **Perfect Dash Parry** | `DASH_PARRY_WINDOW = 0.07s` | Auto-parry within first 0.07s: no damage, full posture restore, riposte window |
| **Refresh on hit** | — | Landing a hit mid-dash restores 1 charge (up to max) |
| **Coyote time** | `DASH_COYOTE_TIME = 0.05s` | Attack/guard allowed 0.05s after dash ends |
| **Wall bounce** | `DASH_WALL_BOUNCE = 0.5` | Dash into wall reflects velocity × 0.5, flips facing |

### Visual Effects

| Effect | Description |
|---|---|
| **Cartoon stretch** | `DASH_STRETCH_X = 1.6`, `DASH_STRETCH_Y = 0.6` (render-only) |
| **Afterimages** | 14 max, spawn every 0.02s, TTL 0.35s with cyan speed tint |
| **Shockwave ring** | Expanding cyan ring on dash start (0.18s) |
| **Curved trail particles** | 0.015s cadence, tapered curved streaks following path |
| **Screen shake** | Light camera trauma (0.4× parry trauma) on dash start |
| **Cyan additive tint** | Dash frame gets `BLEND_RGB_ADD` (100, 200, 255) for energy feel |

### Dash Attack

Bound to `attack4` (`F`, gamepad button 5) and to `light_attack`'s `cancel_into`
chain. It is a lunge move: on the ground the attack state sets
`velocity.x = speed × lunge_speed_multiplier`, so `dash_attack` (1.0 × 350 px/s)
is the strongest opener in the kit.

- **Startup**: 1 frame (was 2)
- **Active**: 8 frames (was 7)
- **Recovery**: 4 frames (was 5)
- **Hitbox**: 70×24 @ (42, -8) (was 60×20 @ (38, -6))
- **Damage**: 16 (was 14), Pierce, super armor break
- **Knockback**: (550, -80) (was 500, -50)
- **Cancels into**: light, heavy, uppercut
- **Cooldown**: 0.50s (was 0.60s)
- **Lunge speed**: 1.0 (was 0.9)
- **From a dash**: pressing `F` mid-dash cancels it into this move once the
  cancel window is open. The `ATTACK` state replaces `DASH`, so the dash
  i-frames and the squished hitbox end with it — the trade for the hitbox.
  `Player.can_attack()` and the `ATTACK` interrupt both read
  `player_states.dash_cancel_open`, so the input gate and the transition can
  never disagree (before this, `can_attack()` forbade `DASH` outright and the
  press was silently swallowed).

### Tuning (`src/core/settings.py`, class `Physics`)

| Field | Default | Meaning |
|---|---|---|
| `DASH_SPEED` | 1100 | Horizontal dash velocity (px/s) |
| `DASH_DURATION` | 0.08 | Dash duration (s) |
| `DASH_FRICTION` | 25.0 | Friction when no input held |
| `DASH_MAX_CHARGES` | 5 | Maximum dash charges |
| `DASH_RECHARGE_TIME` | 0.35 | Time to recharge one charge (s) |
| `DASH_PENALTY_TIME` | 2.0 | Penalty duration when empty (s) |
| `DASH_GRAVITY_MULT` | 0.0 | Gravity multiplier during dash |
| `DASH_CANCEL_WINDOW` | 0.0 | Min dash time before attack/guard cancel (s) |
| `DASH_PARRY_WINDOW` | 0.07 | Auto-parry window from dash start (s) |
| `DASH_REFRESH_ON_HIT` | `True` | Restore 1 charge on hit during dash |
| `DASH_COYOTE_TIME` | 0.05 | Post-dash window for attack/guard (s) |
| `DASH_WALL_BOUNCE` | 0.5 | Velocity retention on wall bounce |
| `DASH_AIR_CONTROL` | 3000.0 | Mid-dash direction change acceleration |
| `DASH_STRETCH_X` | 1.6 | Render stretch horizontal (Renderer) |
| `DASH_STRETCH_Y` | 0.6 | Render stretch vertical (Renderer) |

### Afterimage (`Afterimage`)

| Field | Default |
|---|---|
| `MAX` | 14 |
| `TTL` | 0.35 |
| `SPAWN_EVERY` | 0.02 |

### Dash FX (`src/core/fx.py`)

| Constant | Default |
|---|---|
| `DASH_BURST_COUNT` | 10 |
| `DASH_SHOCKWAVE_TTL` | 0.18 |
| `DASH_SHOCKWAVE_MAX_RADIUS` | 48 |
| `DASH_TRAIL_SPAWN_EVERY` | 0.015 |
| `DASH_TRAIL_TTL` | 0.15 |

### Code Map

- `src/entities/player_controllers.py` — `DashController` (charges, recharge, penalty, `request(move_axis)`, coyote, rollback snapshots)
- `src/states/player_states.py` — `PlayerDashState` (enter/exit/update with direction capture, air control, wall bounce, coyote start), `dash_cancel_open` (the cancel window read by the input gate and the interrupts)
- `src/entities/player.py` — `receive_damage` perfect dash parry branch, `dash.start_coyote()` on exit
- `src/combat/hit_resolver.py` — `_apply_post_effects` dash refresh on hit
- `src/core/level/systems/physics_system.py` — shockwave on dash start, trail particles on cadence, cleanup
- `src/core/level/systems/separation_system.py` — skips separation for invincible entities (phasing)
- `src/core/rendering/renderer.py` — `dash_frame` stretch + cyan tint, afterimage spawning
- `src/core/fx.py` — `DashShockwaveParticle`, `DashTrailParticle`, spawners
- `src/core/asset_library.py` — graceful fallback `dash` → `run` animation
- `src/data/player.py` — `dash_coyote_time` in `PlayerConfig` serialization
