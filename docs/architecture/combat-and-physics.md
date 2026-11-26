# Combat and physics

[Documentation index](../README.md) - [Architecture overview](overview.md) - [Rendering pipeline](rendering.md)

### Physics and assists

Assists are **on**. Set a value to `0` (or `1` for the jump cut) to restore the
legacy, assist-free behaviour. All of them live in `src/simulation/settings.py`.

| Class | Constant | Effect |
|---|---|---|
| `GameFeel` | `JUMP_CUT_DIVISOR` | Variable jump height — releasing the button cuts the rise. |
| `GameFeel` | `GROUND_SNAP_PX` | Sticks to the ground instead of floating off platform edges. |
| `GameFeel` | `STEP_UP_PX` / `CORNER_CORRECT_PX` | Auto-mounts small steps, nudges around ceiling corners. |
| `GameFeel` | `APEX_GRAVITY_DIVISOR` | Reduced gravity at the jump apex, for a longer hang time. |
| `GameFeel` | `FAST_FALL_GRAVITY_MULTIPLIER` | Extra fall acceleration while the down key is held. |
| `Collision` | `MIN_PENETRATION_PX` | Grazes keep sliding instead of stopping dead. |
| `Collision` | `MAX_RESOLVE_PX` | Anti-teleport guard; deeper overlaps flag the entity `crushed`. |
| `PlatformRide` | `STICKY_FACTOR` | Stay mounted on fast-descending platforms. |

### Combat and knockback

Combat is frame-data driven: startup / active / recovery phases feed
`HitboxManager` and `HitResolver` through the two-pass deterministic
`CombatSystem` (`src/simulation/level/systems/combat_system.py`).

| Constant | Effect |
|---|---|
| `Combat.WALL_BOUNCE_FACTOR` | Mid-launch entities rebound off walls (red arrow in debug) instead of stopping dead. |
| `Combat.GROUND_BOUNCE_MIN_SPEED` / `_FACTOR` / `_KEEP` | A launched fighter that lands faster than `MIN_SPEED` rebounds once, keeping `FACTOR` of its fall and `KEEP` of its run. `FACTOR = 0` turns it off. |
| `Combat.KNOCKBACK_MAX_DURATION` | Anti-lock safety for pits. |
| `Physics.REACTION_SLIDE_FRICTION` / `_SLIDE_DRAG` | How a hit fighter slides to a stop on the ground: a constant grip (px/s²) plus a drag (1/s). Shared by hurt, stagger and knockback, so a hit's `power` alone decides how far it sends its target. |
| `Physics.REACTION_AIR_DRAG` | Light horizontal drag while a hit fighter is airborne; `0` keeps the launch speed constant. |
| `Combat.KNOCKBACK_DI_ACCEL` / `_DI_CAP` | Directional influence: an airborne entity can steer its trajectory. |
| `Combat.JUGGLE_DECAY_STEP` / `JUGGLE_DAMAGE_FLOOR` | Diminishing returns on consecutive juggle hits. |
| `Combat.HITSTOP_KNOCKBACK_FACTOR` | Hit-stop scaled to impact magnitude. |
| `Combat.KILL_HITSTOP` / `EXECUTION_HITSTOP` | The least a killing blow, and an execution (a stab, a throw, a death blow), freeze the world. A hit's own `hit_stop` in `attacks.json` replaces the formula: the slash links freeze for two ticks, the finisher for seven. |
| `Combat.OTG_INVULN_DURATION` / `ENEMY_OTG_INVULN_DURATION` | How long a fighter landing from a launch is safe from ground hits: the player is, an enemy is not, so the blow after a launch lands. |
| `Combat.HEAVY_KNOCKBACK_THRESHOLD` | `400` — above it, `CameraShake` is given trauma of `impact / HEAVY_DIV`. |
| `CameraShake.HIT_TRAUMA` / `HIT_DIV` / `KILL_TRAUMA` / `EXECUTION_TRAUMA` | Every landed hit shakes a little, a kill a little more, an execution the most; the strongest of the tick wins. |
| `CameraShake` | `MAX_PX`, `DECAY_PER_S`, `FREQUENCY` — the shake envelope itself. |

Three things decide how far a hit sends its target, and nothing else does:

- the hit's `knockback.power` in `attacks.json` — the speed it gives, in px/s;
- the target's `weight` in `enemies.json` — every knockback it takes is divided
  by it, *before* the launch threshold is read, so one blow launches a slime
  (`0.8`), shoves a goblin (`1.0`) and barely moves a shell (`1.5`);
- the shared friction above (`Physics.REACTION_*`), the same in hurt, stagger
  and knockback.

A hit marked `flinch` in `attacks.json` does not push a grounded target
sideways: the chains' links stun without sending the target out of reach.
An airborne target is pushed as usual, so a juggle still carries.

An enemy the last hit kills leaves the simulation on that tick, and a body in
the FX plane (`CorpseParticle`, tuned by `fx.tuning.Corpse`) carries the hit on:
thrown the way the blow pushed, tumbling, fading. Render-only — it collides with
nothing and no snapshot or golden sees it.

**Enemies choose and take turns.**

- `enemies.json` lists each type's `moves`: an attack, its range and a weight.
- The chase picks one on entry from the enemy's own random stream, so a rollback
  replays the same choice.
- At most `AI.MAX_ATTACKERS` enemies attack at once; the rest wait at striking
  distance, counted from the roster's states rather than stored.
- The goblin and the tooth sweep the floor with a long claw, the slime splashes:
  both can be jumped. The goblin's swipe can meet a slash blade to blade
  (`clash` on both hits).

**A slowed world is the same world on a slower clock.**

- Dark step, prompt and stasis give every entity but the player a share of the
  tick's delta (`Player.world_time_scale`, `PhysicsSystem.process`), including
  platforms, hazards and projectiles. Attacks count frames off that delta, so an
  enemy's swing takes longer.
- Fury, the dark side and blitz do the reverse for the player: the attack clock
  runs fast, and the extra frames go to startup and recovery only. An active
  frame is never skipped — a fast swing hits what a slow one would.

> **Directional influence is not player-gated.** `_apply_directional_influence` in
> `src/simulation/states/reaction_states.py` fires for any entity whose `move_axis` is
> non-zero, and enemies do set `move_axis`. In practice a launched enemy rarely
> carries a stale axis into the air, but the gate is "has an axis", not "is the
> player".

### The ground pivot

> **`turn` is a state, not a delayed facing write.** Reversing on the ground used
> to mirror the sprite on the same frame the axis flipped, so a pivot read as a
> teleport. The velocity curve was never the problem — it always took about a
> third of a second to cross zero. The picture refused to show any of it.

- A delayed facing would be a value every interrupter has to undo, and each
  would need to know the rule exists.
- A state is entered and exited instead: an attack, dash or jump taken mid-pivot
  leaves through `PlayerTurnState.exit`, where the facing is finally committed.
- An attack inside the pivot therefore comes out where the player is pointing —
  no special case to remember.

| Constant | Shipped | Effect |
|---|---|---|
| `Turn.DELAY_S` | `0.14` | How long the pivot holds — just under nine ticks at 60 Hz, the length of the plant. |
| `Turn.MIN_SPEED_PX_S` | `30.0` | Below this the fighter is not travelling, so the flip is immediate and no state is entered. |
| `Turn.BRAKE_CONTROL` | `20.0` | Ground braking on a reversal: bleed toward **zero** at this rate. |
| `Turn.PLANT_PX_S` | `20.0` | …then push out of the plant at this speed. |
| `Turn.LEAD_PX` | `32.0` | Render-only trailing offset of the body, shrinking to zero as the facing lands. |
| `Turn.SKEW_PX` | `20.0` | Shears the frame so the feet stay planted and the top of the body leans over. |
| `Turn.STEP_DISTANCE_PX` / `SPREAD` | `40.0` / `1.15` | The pivot's row in `FootstepDust.TIER`. |

**The pivot is registered in every fighter's state machine** under one shared
name (`Turn.STATE`). Activation is decided by **group and sub-group**, not per
entity:

- groups and sub-groups are named profiles in `settings.PROFILES`, layered by
  inheritance;
- every field is optional, and a layer that omits one inherits it.

| Layer | Where it is named | Ships as |
|---|---|---|
| defaults | `settings.Turn` | off |
| group (one per faction) | `PROFILES["player" / "enemy" / "neutral"]` | only the player is on |
| sub-group (one per enemy type) | `EnemyConfig.turn_profile`, i.e. `"turn_profile"` in `enemies.json` | `null` — takes the group |
| the entity | an attribute set in code | wins over all of the above |

<details>
<summary><b>Measured rationale, worked example, and two state details</b></summary>

**Why braking and accelerating are separate.** A single exponential ease toward
the target is symmetric by construction: the same rate bleeds speed off on the way
to a stop as on the way back up to a run. That is right for one and wrong for the
other. A *reversal* is not that — and a symmetric curve never plants, it crosses
zero without dwelling. At `Physics.FLOOR_CONTROL` a full run crosses in under two
frames, so the deceleration existed and was never seen. *"It turns instantly"*
means not that nothing happens but that what happens is over before the eye has it.

- **Brake toward zero, then plant.** From `PLAYER_SPEED`, a full run sheds
  `251 → 180 → 129 → 92 → 66 → 47 → 34 → 24 px/s` over the eight ticks of
  `DELAY_S`, arriving at the flip standing still.
- **Aiming at zero is the part that matters.** The rate only decides how fast the
  bleed is; aiming at the *target* makes the velocity curve pass through the
  crossing at any rate, so the plant never happens.
- **Airborne is untouched** — a mid-air reversal is a jump turn, and the tighter
  air curve is what makes an air dash feel like an air dash.
- **The lean carries the effect, not the slide.** `LEAD_PX` at 32 px is half the
  sprite's width — 5.5 frames of travel, clear and near its ceiling. A lean has no
  such ceiling, because it cannot detach from anything, which is why raising
  `SKEW_PX` paid far more than raising the slide would have.

**Worked example** — *"all the enemies except the slimes"*. Illustrative: the
repository ships the mechanism, not these entries.

```python
# src/simulation/settings.py — all the enemies take it...
PROFILES["enemy"] = TurnProfile(inherits="default", enabled=True)
# ...except this one, which plants more slowly and leans further.
PROFILES["enemy_goblin"] = TurnProfile(inherits="enemy", brake_control=12.0, skew_px=28.0)
PROFILES["enemy_slime"] = TurnProfile(inherits="enemy", enabled=False)
```

```json
// data/gameplay/enemies.json — which sub-group each type belongs to
{ "goblin": { "turn_profile": "enemy_goblin" } }
```

One entry on for the faction, one off for the type, one string in the type's
config. Nothing in the simulation, the state machine or the renderer knows a
group exists — an entity adopts a name and is done.

- **An unknown profile name is the defaults, not a crash.** A typo gives a fighter
  the shipped behaviour and a game that still starts; a self-inheriting profile
  stops at the cycle rather than hanging at import.
- **The drawing numbers travel with the profile.** `turn_lead_px` and
  `turn_skew_px` live on the entity, not in `settings.Turn`, because the renderer
  is handed a sprite. Left in the settings block they would make a group look
  tunable while the lean quietly ignored it.
- **Per-fighter overrides** win over every named layer: `turn_enabled`,
  `turn_delay_s`, `turn_brake_control`, `turn_plant_px_s`,
  `turn_min_speed_px_s`, `turn_lead_px`, `turn_skew_px`.
- **The hold is installed from the input side.** `PlayerInputHandler` reads input
  in `_pre_update`, *before* the state machine, so a decision taken from a state's
  own `update` would be a frame too late to stop the mirror it is meant to delay.
  `request_turn()` is asked instead of `face_movement()`, and the state keeps the
  mirror frozen with the `facing_locked` tag.
- **The pivot carries the tier it interrupted.** The hold spans the frames where
  the velocity sweeps through `run` / `walk` / `walk_slow`, so resuming from it
  with the live state name would drop `resolve_locomotion_state`'s hysteresis and
  flicker the tier boundaries at the fastest moment.

</details>
