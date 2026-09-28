"""
Centralized game configuration and constants.
"""

import os


class Display:
    """The window's title, and the refresh rate this build targets.

    The starting window size used to live here too, as ``WIDTH``/``HEIGHT``. It
    does not any more: it is derived from the desktop at launch
    (:func:`src.core.display.detection.initial_window_size`), and the window
    manager owns the geometry from then on -- there is no size left for the game
    to hold an opinion about. What the game draws into is a separate question
    again, answered by ``src.core.display.framing``.

    ``FPS`` is the refresh rate this build is written against, and nothing more.
    It is **not** the default frame limit: that is
    ``src.application.settings_store.DEFAULT_FRAME_LIMIT``, because the player
    changes it in the video menu and the two stopped being the same number when
    the frame limit became a setting. ``FPS`` is read in exactly one place, as
    the base of the runaway ceiling ``game.DISPLAY_SAFETY_CEILING_FPS``, so
    raising it cannot silently change what the game presents.
    """

    FPS = 180
    TITLE = "Knightrock"


class World:
    """World and tilemap dimensions."""

    TILE_SIZE = 64

    #: Grid cell edge of both spatial hashes, in world units.
    #:
    #: One number, because there are two hashes and they must agree: the
    #: environment hash the level buckets terrain into, and the entity grid the
    #: pairing systems bucket combatants into. They are queried with the same
    #: rectangles, so a mismatch would not be a performance difference but a
    #: correctness one -- a cell that one of them considers too far away is a
    #: collision the other one cannot see.
    #:
    #: 128 is two tiles: large enough that a 64-unit tile lands in one or two
    #: cells rather than being split four ways, small enough that a query does
    #: not drag half the level in with it.
    HASH_CELL_SIZE = 128


class Physics:
    """Physics and movement constants."""

    PLAYER_SPEED = 350
    GRAVITY = 1500.0
    FALL_GRAVITY = 2800.0
    JUMP_FORCE = 750.0
    MAX_FALL_SPEED = 1500.0
    DASH_SPEED = 1100
    DASH_DURATION = 0.08
    DASH_FRICTION = 25.0
    DASH_MAX_CHARGES = 5
    DASH_RECHARGE_TIME = 0.35
    DASH_PENALTY_TIME = 2.0
    DASH_GRAVITY_MULT = 0.0
    # Dash cancel window (s): how long a dash must last before an attack or a
    # guard can cancel it. 0.0 = cancellable as soon as the dash starts, which
    # is what makes a tapped "dash attack" reachable: interrupts are evaluated
    # before the dash state decrements its timer, so a 0.04 window on a 0.08
    # dash only accepted a press on its very last frame (measured), while 0.0
    # accepts every frame but the first.
    DASH_CANCEL_WINDOW = 0.0
    DASH_PARRY_WINDOW = 0.07
    DASH_REFRESH_ON_HIT = True
    DASH_COYOTE_TIME = 0.05
    DASH_WALL_BOUNCE = 0.5
    CROUCH_HEIGHT_FACTOR = 0.6

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
    # Phase 5 #4 (juggle / advanced hit-stun): stagger scales with damage,
    # juggle gravity lasts one float window, OTG guards knockdown wakeup.
    HITSTUN_DAMAGE_FACTOR = 0.004
    JUGGLE_GRAVITY_TIME = 0.45
    OTG_INVULN_DURATION = 0.5
    DIZZY_DAMAGE_MULT = 1.5
    # P1 sweep CCD (D1): the LOW bound, on measured displacement rather than
    # speed. Euclidean distance between box centres per box index; below this
    # the sweep is pointless (goldens stay stable) and `swept = cur`.
    SWEEP_MIN_DISPLACEMENT_PX = 4.0
    # P1 sweep CCD (D4): the HIGH bound. Past it (respawn, teleport, abnormal
    # carry) `swept = cur`: no giant smear, no phantom touch.
    # Invariant at fixed sim dt (TIMESTEP = 1/60):
    # SWEEP_MAX >= max(MAX_FALL_SPEED, DASH_SPEED, JUMP_FORCE, KB_MAX * 2.0)
    # * TIMESTEP * 1.5  (KB_MAX = the largest magnitude in attacks.json).
    SWEEP_MAX_DISPLACEMENT_PX = 64.0
    SHAPE_SWEEP_MAX_ITERATIONS = 16
    SHAPE_CONTACT_EPSILON_PX = 0.001
    GEOMETRY_CHECKSUM_QUANTUM = 1.0 / 1024.0


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
    POSTURE_COST_MULT = {"light": 1.0, "med": 1.0, "heavy": 1.25}
    BLOCK_MASK_POSTURE = {"any": None, "stand": False, "crouch": True}
    HEIGHT_BLOCK = {
        ("high", False): True,
        ("high", True): False,
        ("mid", False): True,
        ("mid", True): True,
        ("low", False): False,
        ("low", True): True,
        ("overhead", False): True,
        ("overhead", True): False,
    }


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


class ParryFlash:
    """Gold wash over a parrying fighter (render-only, never in snapshots).

    The whole difference between a block and a perfect one on the character
    itself: the reaction animation is already shared, so the parry only
    needs a colour to say that the timing was right.
    """

    DURATION = 0.1
    ALPHA = 0.72


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
    """Landing dust puffs and dash streaks (fx sprites, no collision).

    The three at the top are read by the simulation, not only by the FX:
    ``MIN_FALL_SPEED`` is the threshold that decides whether a landing is
    hard enough to throw dust at all, and the tick is what consumes the
    hint. The rest are the look, and only the FX reads them.
    """

    TTL = 0.4
    COUNT = 6
    MIN_FALL_SPEED = 500.0
    FRAMES_DIR = "assets/graphics/effects/particle"
    FRAME_SCALE = 2.0
    PUFF_RADIUS = 5.0
    RISE = -60.0
    DRAG = 4.0
    FADE_IN = 0.15
    # Where the fan is thrown from, and how hard. The two rows are the
    # horizontal spread of one puff and the vertical kick, jittered.
    SPREAD = 55.0
    SPREAD_JITTER = 20.0
    RISE_RANGE = (60.0, 160.0)
    RISE_ALTERNATE = 40.0
    RADIUS_JITTER = 3.0
    STRENGTH_PER_FALL = 1.6
    STRENGTH_RANGE = (0.6, 2.2)


class FxDash:
    """The dash's own juice: the burst at the start, and what trails it.

    Every one of these is a feel number. ``TRAIL_SPAWN_EVERY`` is also the
    cadence the wind lines ride, because a wind line and a trail mark are two
    halves of the same read and they should not drift apart.
    """

    BURST_COUNT = 10
    WIND_LINES = 2
    TRAIL_SPAWN_EVERY = 0.015
    # The trail comet and the speed line it drags behind it.
    TRAIL_LENGTH = 35.0
    TRAIL_WIDTH = 6.0
    TRAIL_TTL = 0.15
    TRAIL_CURVE = 9.0
    TRAIL_LENGTH_JITTER = (0.8, 1.25)
    TRAIL_WIDTH_JITTER = (0.8, 1.15)
    TRAIL_FADE_IN = 0.1
    STREAK_TTL = 0.22
    STREAK_THICKNESS = 3.0
    STREAK_LENGTH_JITTER = (18.0, 34.0)
    STREAK_SPEED = (500.0, 800.0)
    STREAK_FADE_IN = 0.2
    WIND_THICKNESS = 2.0
    WIND_LENGTH_JITTER = (20.0, 40.0)
    WIND_EXTRA_SPEED = (300.0, 700.0)
    WIND_AHEAD = (0.3, 1.2)
    # The ring on the ground at the start of the dash.
    SHOCKWAVE_RADIUS = 44.0
    SHOCKWAVE_TTL = 0.18
    SHOCKWAVE_STEPS = 5
    SHOCKWAVE_SQUASH = 0.4
    SHOCKWAVE_SCALE = (0.3, 0.7)
    """How far the first step has spread and how much more each step adds, so
    the ring starts small and lands at full size on the last step."""
    SHOCKWAVE_MARGIN = 4
    SHOCKWAVE_RIM = (4, 1)
    """The rim's width from the first step to the last: a shockwave is defined
    by getting lighter as it spreads."""
    # The backward fan the dash start throws: speed, rise, where it starts.
    BURST_SPEED = (140.0, 260.0)
    BURST_RISE = (40.0, 140.0)
    BURST_STEP = 3.0
    BURST_LIFT = 4.0
    BURST_RADIUS_JITTER = (0.0, 2.0)


class FxGuard:
    """The block's ring, and what happens to it when the guard fails.

    A parry is the same arc in gold, so it costs three numbers rather than a
    second set: the colour is the whole difference.
    """

    ARC_RADIUS = 18.0
    ARC_TTL = 0.22
    ARC_FLASH = 42.0
    ARC_FADE_IN = 0.08
    ARC_FALLBACK_OFFSET = 0.3
    """Where the ring stands in front of the defender when the caller has no
    contact point, as a fraction of the body's width."""
    ARC_MARGIN = 4
    ARC_KICK_WIDTH = 2
    # The ring coming apart, on the side the hit landed on.
    SHARD_RADIUS = 20.0
    SHARD_TTL = 0.3
    SHARD_STEPS = 3
    SHARD_PIECES = 18
    SHARD_KICK_PIECES = 9
    SHARD_SPREAD = 0.3
    SHARD_WOUND = 70.0
    SHARD_WOUND_PUSH = 0.9
    SHARD_SHRINK = 0.3
    SHARD_STEP_OPENS = 0.7
    SHARD_DRIFT = (0.4, 1.0)
    SHARD_KICK_DRIFT = (0.6, 1.4)
    SHARD_MARGIN = 2


class FxDizzy:
    """Stars circling the head and the swirl at the feet, for the stun.

    Emitted on their own cadences rather than on the parry that caused the
    stun, so they fade in with the state and are gone shortly after it ends.
    """

    STAR_COUNT = 6
    STAR_RADIUS = 26.0
    STAR_SPEED = 2.4
    STAR_TTL = 1.2
    STAR_SPAWN_EVERY = 0.5
    STAR_BATCH = 2
    STAR_FADE_IN = 0.08
    STAR_RADIUS_JITTER = (0.8, 1.15)
    STAR_PHASE_JITTER = 0.6
    STAR_SIZE = (5.0, 1.5)
    STAR_LIFT = 12.0
    STAR_BOB = 3.0
    VORTEX_TTL = 0.5
    VORTEX_SPAWN_EVERY = 0.12
    VORTEX_RADIUS = 16.0
    VORTEX_FRAMES = 6
    VORTEX_ARMS = 3
    VORTEX_FADE_IN = 0.1
    VORTEX_ARM_REACH = (0.42, 0.62)
    """Alternating arm lengths, as a fraction of the radius, so no two arms
    tile the same wedge and the swirl still closes a full turn."""
    VORTEX_ARM_THICKNESS = 3.0
    VORTEX_ARM_CURVE = 0.4


class FxDecal:
    """The mark a hard landing leaves on the floor."""

    RADIUS = 22.0
    TTL = 0.28
    FADE_IN = 0.05
    MARGIN = 6
    THICKNESS = 5.0
    CURVE = 0.0
    LOBES = ((0.0, 1.0), (2.1, 0.7), (4.2, 0.55))
    """Three tongues fanning off the landing point, as (heading, length).

    A single blob reads as a stain; three at these headings read as the dust
    that was kicked up on impact.
    """


class Sweat:
    """Sweat droplets squeezed out while a drained dasher sits in penalty."""

    TTL = 0.55
    COUNT = 1
    SPAWN_EVERY = 0.22
    RADIUS = 5.0
    MARGIN = 2
    OUTLINE_WIDTH = 2
    POP_UP = -110.0
    GRAVITY = 620.0
    SPREAD = 0.12
    FADE_IN = 0.1
    KICK_X = (30.0, 90.0)
    POP_JITTER = (0.5, 1.0)
    CROWN = (2.0, 7.0)
    TEMPLE = (0.15, 0.5)
    TINT = (0.0, 0.25)


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
    #: Longest frame the accumulator will believe in. Past this the extra time
    #: is dropped, so a hitch cannot be compounded by replaying it.
    #:
    #: Note what that costs: dropping time is not the same as dropping ticks. A
    #: frame that really took 300ms bills 100ms, and the game runs in slow
    #: motion for that frame rather than skipping ahead. ``MAX_TICKS_PER_FRAME``
    #: is the other half of the guard; see the loop.
    MAX_FRAME_TIME = 0.1
    #: Ticks one presented frame may run. Six is a 100Hz frame against a 60Hz
    #: tick rate, which is twice what a player can see; past that the frame is
    #: already lost and catching up only delays the next one -- the spiral.
    MAX_TICKS_PER_FRAME = 6
    MAX_SUBSTEPS_PER_AXIS = 8  # Guard: dash spikes must not spiral (F3.4)


class Input:
    """Input thresholds and buffering windows."""

    AXIS_DEADZONE = 0.1
    DASH_AXIS_THRESHOLD = 0.5
    #: A stick has to travel this far before a menu moves. It was 0.5, which
    #: asks for half the stick's full deflection, and then 0.4, which is still a
    #: third of it. Both read as lag rather than as a stick that has to be
    #: pushed hard: the menu stays where it is while the player pushes, then
    #: moves all at once, and a quick flick to 35% -- the travel most of a
    #: thumb actually makes -- did nothing at all. 0.25 is a quarter of the
    #: deflection, which is where a console menu starts listening, and it is
    #: still twice :data:`AXIS_DEADZONE`, so a stick at rest does not drift the
    #: selection.
    UI_AXIS_TRIGGER_THRESHOLD = 0.25
    #: Below this the direction is considered let go. The 0.10 gap to the
    #: trigger is the hysteresis that stops a stick resting near the threshold
    #: from chattering the selection -- and it is exactly the band between the
    #: two, so a stick held at 0.20 neither moves the menu nor counts as held.
    UI_AXIS_RELEASE_THRESHOLD = 0.15
    #: A stick has to be pushed *this* far before a held direction repeats. It is
    #: a second threshold on purpose, and it is the answer to "one push of the
    #: stick walks the whole menu": a stick is a position, so a hold is not a
    #: press and there is no key to release. Moving asks for a quarter of the
    #: travel and repeating asks for most of it, which is the only way the
    #: player can say "I meant that" -- push harder to scroll, ease back to stop
    #: (easing back is not a step back: the direction is still held).
    UI_AXIS_REPEAT_THRESHOLD = 0.7
    # Held stick: 0.22s before the first repeat, then one step per 60ms. Beyond
    # that (~0.4/0.1) navigation reads as stuck or lagging. The first step is
    # immediate -- SDL triggers it, not this delay.
    UI_REPEAT_INITIAL_DELAY = 0.22
    UI_REPEAT_INTERVAL = 0.06
    ATTACK_BUFFER_WINDOW = 0.2


class Audio:
    """Mixer and interface sound levels (audit UI, lot 5).

    The mixer channel count is deliberately absent. ``pygame.init()`` opens the
    mixer with SDL's two channels, and it only honours a different count when
    ``pygame.mixer.pre_init`` runs *before* it — a later ``init(channels=...)``
    is a documented no-op, so raising it would mean an ordering constraint
    between the bootstrap and the audio module to protect a case that does not
    exist: the per-scene music will stream through ``pygame.mixer.music``,
    which owns its own SDL_music stream and never competes for a channel. Two
    channels is then only an upper bound on overlapping *sound effects*, and a
    navigation tick cutting its own predecessor is what a menu tick should do.
    """

    #: The interface sounds sit under the future music and gameplay effects: a
    #: navigation blip that competes with a track is one the player stops
    #: noticing. The per-category volumes are the seam the settings screen will
    #: drive; nothing persists them yet.
    DEFAULT_VOLUME = 0.6


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


class Locomotion:
    """Movement damping, stop thresholds and ground speed tiers."""

    TURN_DEADZONE = 0.1
    STOP_SPEED_PX_S = 0.5
    RUN_STOP_SPEED_PX_S = 0.1
    WALL_JUMP_DAMPING = 10.0
    VELOCITY_EPSILON = 0.01
    # Ground tiers as |velocity.x| / entity.speed, with hysteresis so the
    # state does not flicker while acceleration crosses a boundary.
    # Demote below *_DEMOTE, promote at/above *_PROMOTE (PROMOTE > DEMOTE).
    WALK_SLOW_DEMOTE = 0.35  # walk -> walk_slow (covers Guard.MOVE_MULT)
    WALK_SLOW_PROMOTE = 0.50  # walk_slow -> walk
    WALK_DEMOTE = 0.65  # run -> walk
    WALK_PROMOTE = 0.80  # walk -> run
    # Enemy patrol cruise as a fraction of chase_speed when config omits
    # an explicit patrol_speed.
    ENEMY_PATROL_SPEED_MULT = 0.5


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
    # Walk tiers reuse the run sprite-sheet with a slower frame clock.
    WALK_FRAME_DURATION = 0.12
    WALK_SLOW_FRAME_DURATION = 0.18
    ATTACK_FRAME_DURATION = 0.07
    HIT_FRAME_DURATION = 0.08


class Gameplay:
    """App-level gameplay rules (Phase 2 #4: SceneManager)."""

    MAX_DEATHS = 3
