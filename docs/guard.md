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
