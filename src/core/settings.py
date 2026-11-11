"""
Centralized game configuration and constants.
"""

import os
from typing import Any, NamedTuple


class Display:
    """The window's title, and the refresh rate this build targets.

    The starting window size used to live here too, as ``WIDTH``/``HEIGHT``. It
    does not any more: it is derived from the desktop at launch -- as large as
    the first panel allows (:func:`src.core.display.monitors.opening_size`), and
    the window manager owns the geometry from then on -- there is no size left
    for the game to hold an opinion about. What the game draws into is a
    separate question again, answered by ``src.core.display.framing``.

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
    # Crouch: the posture shrinks the hurtbox to this fraction of the standing
    # height, and the shrink is interpolated over BLEND_TIME rather than applied
    # in one tick, so entering and leaving it reads as a body moving rather than
    # a hitbox popping.
    CROUCH_HEIGHT_FACTOR = 0.6
    CROUCH_HEIGHT_BLEND_TIME = 0.08
    # Crouch-walk speed as a fraction of the entity's own speed. Deliberately
    # far below ``Guard.MOVE_MULT``: crouching is a defensive posture that
    # shuffles, not a way to travel, and a fighter who can hold it down and
    # cross the level has made the hurtbox shrink optional.
    CROUCH_SPEED_MULT = 0.2

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


class CameraFollow:
    """Follow smoothing, and the speed past which it stops being a follow."""

    #: Fraction of the remaining distance each tick closes. The lag therefore
    #: settles at ``rate / TIMESTEP`` ticks of travel -- 32 world px at 60Hz,
    #: half a tile, which is what keeps the camera from feeling bolted on.
    SMOOTHING_RATE = 8.0

    #: How fast the framing may travel, whatever the gap to close.
    #:
    #: Smoothing an unbounded gap is what turned a death into a whip. The
    #: corpse holds the camera still for the whole respawn window, so by the
    #: time the player is teleported back to the spawn point the camera can be
    #: a couple of thousand units behind -- and closing that at
    #: ``SMOOTHING_RATE`` took it to 20000 px/s, the whole level blurring past
    #: in half a second. The same gap opened on the first tick of every level,
    #: where the camera starts at the world origin and slides to wherever the
    #: player was placed: 1020 units of drift before the player has moved.
    #:
    #: The number is not a taste call. The camera's steady-state speed *is* the
    #: body's speed, and the largest displacement one tick can legitimately
    #: contain is already written down for the collision sweep, which has to
    #: make the same teleport-or-motion judgement:
    #: ``Combat.SWEEP_MAX_DISPLACEMENT_PX / Simulation.TICK_DURATION`` = 3840
    #: px/s. So the cap sits above everything a body can do and can only ever
    #: engage across a discontinuity -- which is the only thing it is for.
    #: ``tests/unit/test_camera_system.py`` holds it to that derivation.
    MAX_SPEED_PX_S = 3840.0


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
    """The dash's entire visual: a few hard-edged copies of the sprite.

    Manga afterimages are not a smear. They are a handful of flat silhouettes
    stamped along the path, each one solid, and they stop. A continuous alpha
    ramp across fourteen of them reads as motion blur instead, which is the
    opposite of the panel it is imitating.

    So the opacity is a ladder rather than a slope: a ghost holds its first
    level, steps down twice, and is gone. And the count can afford to be more
    than three, because the stamps are flat silhouettes -- a row of tinted
    copies of one another blurs into a smear at four, and a row of silhouettes
    still reads as separate shapes.

    The life is kept shorter than the dash recharge so one dash's trail is
    gone before the next one starts.
    """

    MAX = 6
    TTL = 0.22
    SPAWN_EVERY = 0.012
    """One stamp per frame while the dash runs, which is five for an 80ms
    dash. Slower than a frame and the trail thins out; faster and the stamps
    land on top of each other and stop being countable."""
    LEVELS = (255, 170, 90)
    """The opacity ladder, brightest first, walked as the ghost ages.

    A slope between these would be the same as the ramp this replaced, so the
    steps are deliberate: the eye reads discrete plates of tone, which is what
    a manga speed line is drawn with.
    """


class TurnProfile(NamedTuple):
    """One layer of the pivot's tuning. Every ``None`` means "inherit".

    Partial by construction rather than a full set of numbers, because the
    whole point of grouping is that a group says only what it means to say. A
    group that turns the pivot on should not have to restate the delay, the
    brake and the lean in order to be switched on; a sub-group that wants a
    heavier plant should be able to say ``brake_control=12`` and inherit the
    rest. A profile with real numbers in every slot could only be overridden
    wholesale, and then "all enemies take it, except slimes which take it more
    slowly" would need the whole table copied per line.
    """

    inherits: str | None = None
    """The profile this one layers onto, or ``None`` to sit on the defaults."""
    enabled: bool | None = None
    """Whether this layer's fighters take the pivot. Inherited otherwise."""
    delay_s: float | None = None
    brake_control: float | None = None
    plant_px_s: float | None = None
    min_speed_px_s: float | None = None
    lead_px: float | None = None
    skew_px: float | None = None


class Turn:
    """The ground pivot: ``turn``, the state a reversal on the floor enters.

    A fighter running right who presses left used to have both happen at once.
    The velocity eased across zero over about a third of a second while the
    sprite mirrored on the same frame, so the reversal read as a teleport. The
    velocity curve was never wrong; the picture refused to show it.

    The pivot is a **state** and not a delayed facing write, and that is the
    whole design. A delay is a value that has to be undone by everyone who can
    interrupt the thing holding it -- an attack, a dash, a guard, a hit -- and
    each of those has to know the rule exists. A state is the machine's own
    answer: it is entered, it is exited, and anything that interrupts it leaves
    through ``exit``, which is where the facing is finally committed. So "an
    attack pressed inside the pivot still comes out the way the player is
    pointing" is not a special case anyone has to remember; it is what exiting
    the state means.

    What the state buys beyond that:

    * the hold is simulation state, so the rollback snapshot carries it for
      free -- ``StateMachine.save_state`` captures every state's scalars.
    * the dust becomes a row in :data:`FootstepDust.TIER` keyed on the state
      name, the same way a walk and a run are, instead of a flag and a method.
    * ``_footstep_tier`` already asks the state machine rather than the
      velocity, on the documented grounds that re-deriving the tier here would
      put the flicker back. A pivot is a change in the fighter's movement, so
      it belongs in the machine that classifies movement.

    The one thing the state cannot do is hold the facing by itself, and the
    reason is the loop's order: the player reads input in ``_pre_update``,
    which runs before the state machine, so the mirror has already happened by
    the time any state runs. The freeze is therefore installed from the input
    side -- :func:`src.states.turn_state.request_turn` is asked *instead of*
    ``face_movement`` -- and the state keeps it with the ``facing_locked`` tag.

    :data:`DELAY_S` at 0 is not "legacy": the state is simply never entered,
    because ``request_turn`` declines to enter it.
    """

    STATE = "turn"
    """The state name every fighter's machine registers the pivot under.

    One shared string rather than a member of each enum, because
    :func:`src.states.turn_state.request_turn` has to name a state in a machine
    it knows nothing about. ``PlayerState.TURN`` and ``EnemyState.TURN`` are
    both this value and a test holds them to it -- the alternative is a state
    name that quietly differs between fighters, which is exactly the kind of
    thing that reads as "the pivot works for the player".

    Availability is global and activation is not. Every fighter's machine
    registers :data:`STATE`, so the pivot is there to be switched on;
    ``turn_enabled`` on the entity is what decides whether it is.
    """

    DELAY_S = 0.14
    """How long the pivot holds, in seconds.

    Just under nine ticks at 60Hz, and -- this is the number that matters --
    the length of the plant that :data:`BRAKE_CONTROL` produces.

    The hold is *tied to the plant*, not chosen for its own sake, and the two
    were walked together: 0.14 is what ``BRAKE_CONTROL = 20`` takes to bleed a
    full run down to :data:`PLANT_PX_S`. So the fighter spends the whole hold
    visibly shedding speed and arrives at the facing flip standing still, with
    the mirroring and the braking ending on the same tick.

    That alignment is the whole reason it is not longer. The hold went
    0.09 -> 0.16 -> 0.20 -> 0.10 -> this, and the climb chased the wrong
    symptom: a longer hold felt *worse*, because it stretched the window in
    which the fighter is visibly travelling one way while looking the other.
    A hold is the lean and the plant, not a delay on its own; :data:`LEAD_PX`
    and :data:`SKEW_PX` are what carry the weight.

    Set to 0, the state is never entered and the mirror is instant, as before.
    """
    MIN_SPEED_PX_S = 30.0
    """Ground speed above which a reversal is worth a state at all.

    Below this the fighter is effectively stationary and the flip is applied the
    same frame, with no state entered. A turn taken from a standstill has no
    momentum to announce, and holding the facing there would only add latency
    to something the player read as deliberate.

    Lower than the 60 it started at, and for a reason that only became true once
    :data:`BRAKE_CONTROL` existed: a slow walk now *plants* rather than curving,
    because the brake aims at zero. A reversal at 40 px/s stops at 20, dwells a
    frame and pushes -- which is exactly the shape of the effect at full speed,
    only smaller. Skipping it there would have meant the pivot appearing only
    above some speed and reading as a special case of itself.
    """
    LEAD_PX = 32.0
    """Horizontal sprite offset at the start of the pivot, shrinking to zero.

    Render-only, in pixels of screen rect, so it cannot touch the hitbox.

    The number that sets the scale is the fighter's *speed*, not the sprite's
    width. At ``PLAYER_SPEED`` the fighter covers 5.8 pixels per frame, so the 6px
    this started at was one frame of travel and the 12px it became was two.
    Both read as a jitter on a couple of frames, and a jitter is what you see
    when something is wrong rather than when a character pivots.

    Thirty-two is five and a half frames of travel at a full run, and two thirds
    of the player's width -- an offset you cannot miss, while the sprite still
    overlaps the hitbox it is drawn over. That overlap is the ceiling and the
    reason not to go further: past roughly the sprite's own width the fighter
    stops looking like a fighter sliding along and starts looking like a
    fighter pasted next to one, which is a bug with a nicer frame.

    :data:`SKEW_PX` carries more of the effect than this does, and it can be
    pushed further, because a lean cannot detach from anything.
    """
    SKEW_PX = 20.0
    """How far the sprite's top edge leans over, in pixels, at the start.

    The offset alone slides a sprite, and nothing in a slide says *leaning*; a
    fighter throwing his weight around is one whose body is not vertical. This
    shears the frame instead: the feet stay exactly where they were and only
    the top goes over, which is what a pivot looks like from the side.

    This is the number that carries the effect, and the reason is worth
    keeping: at 9 it was a **7.7 degree** lean on a 56-pixel sprite, which is
    under the threshold at which the eye reads a change of pose at all. At 20 it
    is about **20 degrees** -- the silhouette is broken, the character is
    unmistakably off its feet-line, and the outline is still the same outline.

    A shear rather than a rotation, because a rotation lifts the feet off the
    floor at this amplitude, which is the difference between a character and a
    bug. And a shear rather than a squash, because the animation's own jump and
    dash frames already change the silhouette's height and this would be read
    as one of those instead.
    """
    BRAKE_CONTROL = 20.0
    """Ground damping applied while the input opposes the current velocity.

    The reversal was already decelerating -- it is an exponential ease toward
    the target either way -- but it was doing it at :data:`Physics.FLOOR_CONTROL`
    in *both* directions, and a symmetric curve is a curve: it never plants. The
    fighter crossed zero in under two frames, so the deceleration existed and
    was never seen. That is what "it turns instantly" means in practice -- not
    that nothing happens, but that what happens is over before the eye has it.

    This is the brake half, and it is higher than the acceleration rate so the
    bleed is quick and unmistakable. At 20 a full run comes down through 243,
    168, 117, 81, 56, 39 and 27 px/s in eight frames. It was 30, which did the
    same job in five -- and five frames of a slow-down is the difference between
    a change of speed and a stop.

    The rate is not the interesting number, though; the interesting number is
    what it aims at. The bleed aims at **zero**, not at the new direction, and
    that is the whole trick. Easing toward the target makes the velocity curve
    through the crossing without ever dwelling there -- at any rate -- so the
    fighter is always moving and a plant never happens. Aiming at zero makes him
    actually stop, and the push then starts from a plant.

    Not so high that it becomes friction: at this rate the deceleration is still
    visibly a ramp rather than a stop, which is what keeps a pivot from reading
    as the fighter hitting a wall. 0 restores the old single-rate curve exactly.
    """
    PLANT_PX_S = 20.0
    """Ground speed below which a reversal has planted and the push begins.

    The switch between the two halves, and deliberately small. A plant is the
    fighter standing still for a moment, so the threshold has to be low enough
    that the velocity actually reaches it -- at 45 px/s the brake stopped being
    asked while the fighter was still doing a sixth of his top speed, and the
    "plant" was a curve with a label on it.

    Not zero, because exactly zero would hand the push a single exponential
    leap as its first frame. 20 px/s is a real stand -- about a fifteenth of
    the player's top speed -- and it is where the friction starts from rather
    than a dead stop the fighter has to be pushed all the way out of.
    """
    STEP_DISTANCE_PX = 40.0
    """Ground covered before a pivoting fighter scuffs the floor again.

    A row in :data:`FootstepDust.TIER` like ``walk`` and ``run``, so the pivot
    marks the floor by cadence and nothing has to know it happened. Sized for
    about one mark over the whole hold: a fighter crossing zero covers roughly
    thirty-five pixels on the way, so a shorter stride would draw the dash
    trail small and a longer one would draw nothing at all.
    """
    SPREAD = 1.15
    """The pivot's share of the footstep spread: the run row, unchanged.

    A pivot is not a scuff, so the two halves separate the way they do at a
    run -- one mark under the trailing heel rather than a paired line down the
    middle of a path.
    """


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

    #: Design sizes of the debug text, in the menu's pixel font: snapped to its
    #: 8-pixel grid (``menu_font_size``), so 10 is 8 px at the design size and
    #: 16 px from a density of 1.25.
    FONT_SIZE = 10
    TITLE_FONT_SIZE = 10
    LABEL_FONT_SIZE = 10

    #: World-space label cards floating above entities: as small as the font
    #: draws, so a card stays compact next to a ~48 px tall sprite.
    WORLD_TITLE_FONT_SIZE = 8
    WORLD_LABEL_FONT_SIZE = 8

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


def resolve_turn_profile(name: str) -> TurnProfile:
    """Flatten ``name``'s inheritance chain into one fully-populated profile.

    Nearest layer wins, and the chain is walked root-first so a sub-group only
    has to state what it changes. An unknown name resolves to the defaults
    rather than raising: this is tuning, and a level that names a group nobody
    defined should get the shipped behaviour and a game that still starts, not
    a crash on the first spawn. A cycle is broken the same way -- the walk stops
    revisiting names, so a typo that points a profile at its own descendant
    costs the most specific values rather than hanging.

    Reads :data:`PROFILES` directly. It used to take the table as an argument so
    a test could pass its own, and that turned out to be a way of doing things
    twice: the test could equally add to the real table and let it be restored,
    and the argument was a second code path through this function that nothing
    in the game ever took.
    """
    profiles = PROFILES
    if name not in profiles:
        return TurnProfile(
            enabled=False,
            delay_s=Turn.DELAY_S,
            brake_control=Turn.BRAKE_CONTROL,
            plant_px_s=Turn.PLANT_PX_S,
            min_speed_px_s=Turn.MIN_SPEED_PX_S,
            lead_px=Turn.LEAD_PX,
            skew_px=Turn.SKEW_PX,
        )

    chain: list[TurnProfile] = []
    seen: set[str] = set()
    cursor: str | None = name
    while cursor is not None and cursor in profiles and cursor not in seen:
        seen.add(cursor)
        profile = profiles[cursor]
        chain.append(profile)
        cursor = profile.inherits
    chain.reverse()

    merged: dict[str, Any] = {
        "enabled": False,
        "delay_s": Turn.DELAY_S,
        "brake_control": Turn.BRAKE_CONTROL,
        "plant_px_s": Turn.PLANT_PX_S,
        "min_speed_px_s": Turn.MIN_SPEED_PX_S,
        "lead_px": Turn.LEAD_PX,
        "skew_px": Turn.SKEW_PX,
    }
    for profile in chain:
        for field in (
            "enabled",
            "delay_s",
            "brake_control",
            "plant_px_s",
            "min_speed_px_s",
            "lead_px",
            "skew_px",
        ):
            value = getattr(profile, field)
            if value is not None:
                merged[field] = value
    return TurnProfile(**merged)


#: Named tuning layers, from the most general to the most specific.
#:
#: This is the whole configuration surface for groups. An entity names one and
#: is done: a fighter class picks the group it belongs to in its own
#: constructor, and a per-type sub-group is a matter of naming it in that type's
#: config. Nothing else in the codebase has to know the group exists.
#:
#: The shipped set is deliberately small and says almost nothing, because the
#: defaults should keep saying nothing too: only the player takes the pivot,
#: and every other fighter inherits that off. Adding a line here is how a group
#: of enemies is switched on.
PROFILES: dict[str, TurnProfile] = {
    "default": TurnProfile(),
    "player": TurnProfile(inherits="default", enabled=True),
    "enemy": TurnProfile(inherits="default"),
    "neutral": TurnProfile(inherits="default"),
}
"""Profile per faction, which is the one grouping every fighter already has.

``Player`` takes ``"player"`` and every ``Enemy`` takes ``"enemy"``, so the
shipped table is a no-op over the defaults apart from the player -- and that is
the point of it existing. Switching the pivot on for a whole faction is one
entry, and an entity that belongs to no named group is simply off.
"""


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
