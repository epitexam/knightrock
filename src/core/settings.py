"""
Centralized game configuration and constants.
"""

import os


class Display:
    """Display and rendering settings."""

    WIDTH = 1440
    HEIGHT = 900
    SIZE = (WIDTH, HEIGHT)
    # Simulation runs at 60 Hz (Simulation.TICK_RATE); rendering at 120 FPS
    # keeps motion smooth without redrawing the same state 2 frames out of 3
    # as the previous 180 FPS setting did (audit F1.4/F6.1).
    FPS = 180
    TITLE = "Knightrock"


class World:
    """World and tilemap dimensions."""

    TILE_SIZE = 64


class Physics:
    """Physics and movement constants."""

    PLAYER_SPEED = 350
    GRAVITY = 1500.0
    FALL_GRAVITY = 2800.0
    JUMP_FORCE = 750.0
    MAX_FALL_SPEED = 1500.0
    DASH_SPEED = 1000
    DASH_DURATION = 0.10
    DASH_FRICTION = 15.0
    DASH_MAX_CHARGES = 5
    DASH_RECHARGE_TIME = 0.40
    DASH_PENALTY_TIME = 2.20
    DASH_GRAVITY_MULT = 0.0

    FLOOR_CONTROL = 25.0
    AIR_CONTROL = 12.0
    WALL_SLIDE_SPEED = 100.0
    COYOTE_DURATION = 0.12
    JUMP_BUFFER_DURATION = 0.10

    # Drag coefficients
    DRAG_COEFFICIENT = 0.08
    FALL_DRAG_COEFFICIENT = 0.12
    MAX_SLIDE_SPEED = 80.0

    HURT_FRICTION = 5.0
    KNOCKBACK_FRICTION = 8.0
    STAGGER_FRICTION = 8.0
    DASH_AIR_CONTROL = 3000.0


class Combat:
    """Combat, damage, and stagger mechanics."""

    HURT_DURATION = 0.4
    PLAYER_HURT_DURATION = 0.12
    INVINCIBILITY_DURATION = 0.18
    HITSTOP_BASE = 0.05
    HITSTOP_DAMAGE_FACTOR = 0.002
    HURT_DURATION_KNOCKBACK_SCALE = 0.0002
    STAGGER_DURATION = 0.25
    PLAYER_STAGGER_DURATION = 0.15
    SUPER_ARMOR_THRESHOLD = 3
    COMBO_WINDOW = 0.5
    CONTACT_DAMAGE_THRESHOLD = 300.0
    CONTACT_DAMAGE_AMOUNT = 5.0
    HEAVY_KNOCKBACK_THRESHOLD = 400.0
    ENEMY_FLOOR_CONTROL = 20.0
    ENEMY_AIR_CONTROL = 10.0
    # Safety cap: a launch always releases, even if the floor never comes
    # (pit falls). Normal ground knockbacks resolve well below this.
    KNOCKBACK_MAX_DURATION = 2.0
    # Wall bounce: launched entities rebound instead of stopping dead.
    # 0.0 = legacy full stop.
    WALL_BOUNCE_FACTOR = 0.4
    # Extra hit-stop per knockback magnitude unit (px/s).
    HITSTOP_KNOCKBACK_FACTOR = 0.0002
    # Directional influence while airborne in knockback (hold to steer).
    KNOCKBACK_DI_ACCEL = 500.0
    KNOCKBACK_DI_CAP = 200.0
    # Juggle scaling: consecutive air hits decay toward this floor.
    JUGGLE_DECAY_STEP = 0.1
    JUGGLE_DAMAGE_FLOOR = 0.5
    # Phase 5 #4 (juggle / hit-stun avancé): stagger scales with damage,
    # juggle gravity lasts one float window, OTG guards knockdown wakeup.
    HITSTUN_DAMAGE_FACTOR = 0.004
    JUGGLE_GRAVITY_TIME = 0.45
    OTG_INVULN_DURATION = 0.5
    DIZZY_DAMAGE_MULT = 1.5


class Guard:
    """Directional guard with chip damage, parry window, and posture break."""

    MAX_POSTURE = 100.0
    REGEN_PER_S = 35.0
    CHIP_RATIO = 0.15
    POSTURE_COST_RATIO = 2.0
    PARRY_WINDOW = 0.15
    RIPOSTE_WINDOW = 0.6
    MOVE_MULT = 0.35
    AIR_POSTURE_MULT = 1.5
    PUSH_FACTOR = 0.15
    BREAK_LOCKOUT = 1.2
    BREAK_STAGGER = 1.0
    PARRY_HITSTOP = 0.14
    PARRY_TRAUMA = 0.45
    BREAK_TRAUMA = 0.55
    GUARD_TRAUMA = 0.12


class CameraShake:
    """Deterministic impact shake (sine-based, fixed-timestep safe)."""

    MAX_PX = 10.0
    DECAY_PER_S = 2.5
    FREQUENCY = 90.0
    # Impact magnitude (px/s) mapping to full trauma.
    HEAVY_DIV = 1200.0


class HitFlash:
    """White damage flash overlay (render-only, never in snapshots)."""

    DURATION = 0.09


class ReactionMark:
    """Freshness window of a hit reaction in the debug overlay (render-only).

    ``ReactionComponent`` re-arms the owner's ``reaction_age`` to this value
    every time a reaction fires; ``Entity.update`` decays it. Never
    snapshotted, never in goldens (``flash_timer`` precedent).
    """

    DURATION = 0.4


class Afterimage:
    """Dash ghost trail (render-only)."""

    MAX = 14
    TTL = 0.35
    SPAWN_EVERY = 0.02


class Dust:
    """Landing dust puffs and dash streaks (fx sprites, no collision)."""

    TTL = 0.4
    COUNT = 6
    MIN_FALL_SPEED = 500.0


class Sweat:
    """Sweat droplets squeezed out while a drained dasher sits in penalty."""

    TTL = 0.55
    COUNT = 1
    SPAWN_EVERY = 0.22


class Ledge:
    """Ledge (void-edge) detection and avoidance tuning."""

    # Probe ahead of the front foot: no collider inside means void below.
    PROBE_AHEAD_PX = 14.0
    PROBE_DROP_PX = 30.0
    PROBE_SKIN_PX = 4.0
    # Beat held in the shared ledge state after turning from the void.
    HOLD_DURATION = 0.3
    # Horizontal friction stopping the entity during that beat.
    STOP_FRICTION = 25.0


class EnemyJump:
    """Chase-hop triggers for jump-capable enemy types (Goblin)."""

    # Player feet this far above the enemy head count as "above".
    PLAYER_ABOVE_MARGIN_PX = 16.0
    # Horizontal window inside which the enemy hops toward the player.
    SEEK_RANGE_PX = 220.0
    # Gap jumps: scan step, level tolerance with the player, deepest
    # landing below the feet, and safety margins on the physics range.
    GAP_SCAN_STEP_PX = 8.0
    GAP_LEVEL_PX = 80.0
    MAX_LANDING_DROP_PX = 160.0
    RANGE_SAFETY = 0.8
    RISE_SAFETY = 0.7
    # Bold moves (jumpers only): drop after a player below when a floor
    # catches the fall, or leap a slightly-too-wide/too-deep gap.
    DROP_SEEK_PX = 320.0
    RISK_DROP_PX = 320.0


class Separation:
    """Collision separation and resolution constants."""

    SEARCH_INFLATE = 400
    SUB_STEP_SIZE = 16.0
    STRENGTH = 0.65
    VERTICAL_STACK_RATIO = 0.4


class Debug:
    """Debug overlay settings."""

    FONT_SIZE = 24
    LABEL_FONT_SIZE = 16

    #: World-space label cards floating above entities: much smaller than
    #: the side debug panels, so a 2-row card stays compact next to a
    #: ~48 px tall sprite instead of dwarfing it.
    WORLD_TITLE_FONT_SIZE = 14
    WORLD_LABEL_FONT_SIZE = 12

    @staticmethod
    def is_enabled() -> bool:
        """Return True when the debug overlay is enabled.

        The environment variable is read at call time (not at import time)
        so that ``main_debug()`` can enable the overlay after the module
        hierarchy has already been imported (BUG-02).
        """
        return os.getenv("DEBUG", "0") == "1"


class Simulation:
    """Fixed timestep and simulation loop settings."""

    TICK_RATE = 60
    TICK_DURATION = 1.0 / TICK_RATE
    TIMESTEP = TICK_DURATION
    # Rollback tuning (audit F2.5, Phase 3 #3): MAX_PREDICTION_FRAMES sizes
    # the local RollbackSystem ring buffer; ROLLBACK_FRAMES is the per-request
    # rewind depth a future netcode transport will cap re-simulation at.
    MAX_PREDICTION_FRAMES = 8
    ROLLBACK_FRAMES = 4
    MAX_FRAME_TIME = 0.1  # Maximum frame time to prevent spiral of death
    MAX_SUBSTEPS_PER_AXIS = 8  # Guard: dash spikes must not spiral (F3.4)


class Input:
    """Input thresholds and buffering windows."""

    AXIS_DEADZONE = 0.1
    ATTACK_BUFFER_WINDOW = 0.2


class Collision:
    """Collision probes and contact tolerances (F3.1)."""

    CONTACT_SKIN_PX = 4.0
    PROBE_THICKNESS_PX = 2.0
    PROBE_WIDTH_PX = 2.0
    WALL_PROBE_OFFSET_PX = 2.0
    # Robustness (Phase B): only zero the velocity on the resolved axis when
    # the penetration exceeds this depth; grazes keep sliding. 0.0 = legacy
    # full stop on every touch.
    MIN_PENETRATION_PX = 2.0
    # Clamp the axis-nearest fallback correction (deep-overlap teleport guard);
    # beyond it the entity is flagged crushed instead. inf = legacy unbounded
    # teleport.
    MAX_RESOLVE_PX = 16.0


class PlatformRide:
    """Moving-platform mount tolerances (F3.1)."""

    SNAP_EPSILON_TOP_PX = 4.0
    SNAP_EPSILON_BOTTOM_PX = 2.0
    # Sticky carry on fast-descending platforms: the mount window grows with
    # the platform's downward step. 0.0 = legacy fixed window (detach).
    STICKY_FACTOR = 0.5


class GameFeel:
    """Game-feel assists. Set 0 (or 1 for the jump cut) to go legacy/neutral."""

    # Rising velocity is divided by this on jump release (variable jump).
    JUMP_CUT_DIVISOR = 2.5
    # Snap down to ground within this distance instead of floating off edges.
    GROUND_SNAP_PX = 3.0
    # Auto-mount ledges this tall while grounded (no jump needed).
    STEP_UP_PX = 8.0
    # Lateral nudge when jumping into a ceiling corner.
    CORNER_CORRECT_PX = 12.0
    # Reduced gravity while |velocity.y| stays under this threshold at the
    # jump apex: a longer hang to fine-tune edge crossings.  Set the divisor
    # to 1.0 to disable the apex hang entirely.
    APEX_GRAVITY_DIVISOR = 2.0
    APEX_VELOCITY_THRESHOLD_PX_S = 120.0
    # Falling acceleration is multiplied by this while the down action is
    # held (fast fall); 1.0 keeps the legacy single fall curve.
    FAST_FALL_GRAVITY_MULTIPLIER = 1.5
    # Edge drift range at the apex (px/s) granted by the reduced gravity:
    # derived as threshold / (1 - 1/divisor); documented in tests.
    APEX_DRIFT_BUDGET_PX_S = 120.0 / (1.0 - 1.0 / 2.0)


class Locomotion:
    """Movement damping and stop thresholds."""

    TURN_DEADZONE = 0.1
    STOP_SPEED_PX_S = 0.5
    RUN_STOP_SPEED_PX_S = 0.1
    WALL_JUMP_DAMPING = 10.0
    VELOCITY_EPSILON = 0.01


class AI:
    """Enemy perception thresholds."""

    CHASE_STOP_DISTANCE_PX = 10.0


class Respawn:
    """Player respawn and debug spawn tuning."""

    DELAY_S = 2.0
    DEBUG_SPAWN_COOLDOWN_S = 0.5


class StateMachineConfig:
    """State machine configuration constants."""

    HISTORY_MAXLEN = 16  # Maximum number of states to keep in history


class Animation:
    """Sprite animation tuning (Phase 2 #1: AssetLibrary + Animator)."""

    FRAME_DURATION = 0.10
    RUN_FRAME_DURATION = 0.08
    ATTACK_FRAME_DURATION = 0.07
    HIT_FRAME_DURATION = 0.08
    HAZARD_FRAME_DURATION = 0.12


class Gameplay:
    """App-level gameplay rules (Phase 2 #4: SceneManager)."""

    MAX_DEATHS = 3
