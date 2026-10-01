"""
Centralized game configuration and constants.
"""

import os
from typing import NamedTuple


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


class Dust:
    """Landing dust: a low sheet of grit thrown out of the feet on a hard landing.

    The three at the top are read by the simulation, not only by the FX:
    ``MIN_FALL_SPEED`` is the threshold that decides whether a landing is
    hard enough to throw dust at all, and the tick is what consumes the
    hint. The rest are the look, and only the FX reads them.

    The look is a sheet, not a ball. A landing used to throw six clouds built
    from four overlapping discs each, with a disc of highlight set into the top
    left of every one of them, and the frame it produced was six small shiny
    spheres: the puff's whole silhouette came out as a smooth convex ellipse
    about as wide as the fighter, which is a bubble rather than a kick. So the
    cloud is now a *low band of small parts* -- a connected base and a
    scattered fringe, most of them chips rather than discs -- with an irregular,
    notched top edge, lit by a one-pixel rim and sitting in its own shadow, and
    it is about half the width it was.

    The grains that make it read as dust rather than as smoke are a separate
    family, :class:`DustGrain`, thrown around this one.
    """

    TTL = 0.4
    COUNT = 4
    MIN_FALL_SPEED = 500.0
    PUFF_RADIUS = 6.0
    RISE = 60.0
    """Downward, so a kicked sheet decelerates and settles.

    It used to be negative, and the sign is the whole argument. Used as a
    gravity, a negative ``RISE`` accelerates the sheet *upward* for its entire
    life, so a landing dust climbed for all four tenths of a second and ended
    its fade above the fighter's head -- which is smoke off a fire, and the
    reading the dash trail had already refused to make for the same reason.

    With gravity downward the kick is a kick: the sheet leaves the floor fast,
    slows through its arc, and is already coming back down when it fades. The
    number is set so the strongest landing peaks a little under twenty pixels
    up against a forty-eight-pixel fighter, which is high enough to read as
    thrown and low enough to stay attached to the floor it came off.
    """
    DRAG = 4.0
    FADE_IN = 0.15
    FOOT_SPREAD = 0.3
    """Where along the fighter the fan is laid out, as a share of his width.

    Across his whole footprint rather than bunched at the centre of it, and
    this is not a placement detail. The FX plane is painted *under* the moving
    layer, so a puff thrown from the middle of a forty-wide fighter spends its
    first third of life invisible behind him -- and the first third of a
    landing is the only part of it anybody is looking at. Laid across the feet,
    the outer two of the fan are clear of the body from the frame they are
    born on.
    """
    # Where the fan is thrown from, and how hard. The two rows are the
    # horizontal spread of one puff and the vertical kick, jittered.
    SPREAD = 55.0
    SPREAD_JITTER = 20.0
    RISE_RANGE = (12.0, 34.0)
    """The upward speed each sheet is kicked to, as a range.

    Down from the ``(60, 160)`` this had, and the reason is the arc rather than
    the peak: with ``RISE`` now pulling downward there is nothing to stop a
    sheet but its own drag on the horizontal, so this number *is* the height it
    reaches, reached at the end of its life rather than in the middle of it.
    Thirty-four at the top of the range, times the strongest landing and the
    alternate below, is twenty pixels of arc on a forty-eight-pixel fighter.
    """
    RISE_ALTERNATE = 8.0
    """The extra kick every other sheet in the fan gets.

    Small, and it stacks on top of ``RISE_RANGE`` rather than replacing part of
    it, so it has to stay small: at the ``40.0`` this had it was on its own
    responsible for a third of the arc, and the alternation it exists to create
    -- a fan that does not rise as one flat front -- was not worth the fighter's
    head.
    """
    RADIUS_JITTER = 1.5
    STRENGTH_PER_FALL = 1.2
    STRENGTH_RANGE = (0.7, 1.5)
    """How big the whole landing reads, at the fall speed that caused it.

    Capped much lower than the ``2.2`` it used to allow. A puff is thrown out
    of a forty-wide fighter's feet, and at the top of the old range a hard
    landing put a puff fifty pixels across on each side of him -- wider than
    the thing that landed. That is not a dust effect, it is a cloud the
    character is standing inside, and no amount of good shading rescues a
    silhouette that is the wrong size.
    """

    # --- the sheet -----------------------------------------------------------
    # A puff used to be a single disc that faded, which read as a ball being
    # switched off. It then became four large overlapping discs, which read as
    # a bubble. It is now a band of many small ones: the same technique, at a
    # scale where the individual lobes stay visible, which is what turns a
    # silhouette back into material. The steps are a shared ladder, one per
    # size, so a fan of four is four references into a table rather than four
    # painted surfaces.
    PUFF_STEPS = 4
    PUFF_BUCKETS = (3, 5, 7, 9, 12)
    """The radii a puff is painted at, smallest first.

    Discrete on purpose, for the same reason the alpha is: a continuous radius
    would mean a surface per particle, and a landing can put four on screen at
    once. Snapping to a bucket means the ladder is built once per session and
    shared, and the eye reads the small step between two sizes as a puff
    opening rather than as a jitter in size.

    A shorter table than it had, because the radii it lists are smaller. Every
    entry is a whole ladder of four surfaces kept alive for the session, so
    the buckets are priced and a bucket nobody can reach is dead weight.
    """
    PUFF_GROWTH = 0.14
    """How much further the sheet reaches at each step, as a share of the
    radius it started at. The last step is drawn at ``1 + growth * (steps-1)``.

    Kept small on purpose. This is the radius *along the ground*, and a puff
    thrown out of a forty-wide fighter's feet that ends three times wider than
    it started is not a billow, it is a cloud that swallowed the character.
    """
    PUFF_STEP_OPENS = 0.55
    """The share of the life the sheet takes to open over. The rest of the
    life is spent drifting and fading, so a puff finishes spread and gone."""
    PUFF_MOTES = 11
    """How many parts the sheet is built from.

    Many and small, where it was four and large, but not as many as it was on
    the way here. Four parts of comparable radius, each overlapping the others,
    sum to one smooth convex outline and no amount of offsetting them changes
    the fact that the result is an ellipse. Many small ones leave notches along
    the top and a scatter of shoulders.

    Eleven rather than fifteen because the count trades against the size, and a
    part too small to show a side is a speck: at fifteen the chips had shrunk
    to two pixels and the outline went back to being made of little arcs, which
    is the thing the chips are there to stop. Fewer and larger is what buys a
    facet a chance to read as one.
    """
    PUFF_BASE_SHARE = (0.26, 0.36)
    """The lower band's lobes, as shares of the radius, across a range.

    Half the lobes, at the bottom, and the only ones large enough to touch
    each other. This is the band that has to be *connected*: it is what makes
    the mark one mass rather than a handful of dots, and it is why these
    lobes are bigger and closer together than the fringe above them rather than
    drawn from the same distribution. One draw for both was tried and it fails
    badly -- the spread that gives the top edge its notches is the same spread
    that pulls the bottom parts out of each other's reach, and the sheet comes
    out as a row of separate puffs hanging in the air.
    """
    PUFF_TOP_SHARE = (0.1, 0.16)
    """The fringe's lobes, as shares of the radius, across a range.

    Under the base band's smallest, so the top edge is finer than the bottom
    and the silhouette tapers upward the way a spread of dust does. A fringe at
    the base band's size tiles into a scalloped row, which is the other way to
    say "cartoon" without drawing a single circle.
    """
    PUFF_MOTE_SPREAD = 0.94
    """How far the band reaches either side of its centre, as a share of the radius.

    Near the radius itself, so the sheet's own width-to-height ratio is close
    to a circle's -- and the silhouette is wide and shallow in the *layout*
    rather than by squashing a round mass, which is what it used to be. A
    landing had been drawing a disc that was quietly flattened; a band of small
    lobes gets the same proportion with no disc in it to be round.
    """
    PUFF_MOTE_RISE = (0.1, 0.45)
    """How far above the band's floor the fringe sits, as a share of the radius.

    The whole silhouette comes out of this range. A fringe drawn within a band
    narrower than a lobe is tall merges with the base into one flat top, and a
    flat top is a drawn shape; drawn across a range several lobes wide, the
    fringe overlaps the base in places and stands clear of it in others, and
    that alternation is the notch.
    """
    PUFF_MOTE_BASELINE = 0.34
    """Where the band's own floor sits, as a share of the radius below centre.

    Below the centre rather than on it, so the sheet's weight is in its lower
    two thirds. Centring the band put as much dust above the fighter's feet as
    below, and dust that has been kicked does not hang.
    """
    PUFF_MOTE_EVERY = 3
    """Every ``n``-th fringe part is drawn at the top of ``PUFF_TOP_SHARE``.

    Grit is not uniform: a few grains are coarse and most are fine, and a fringe
    of identical specks reads as noise rather than as debris. The spacing is a
    stride rather than a draw so that every sheet gets the same few coarse
    lobes -- which is what keeps a fan from being four different noises.
    """
    PUFF_CHIP_SHARE = 0.72
    """The share of the sheet's parts drawn as chips rather than discs.

    This is the number the shape turns on, and it is high because every arc on
    a silhouette is a bubble however small it is. Fifteen little circles make
    fifteen small bubbles along the outline, and what the eye reads is the arcs
    rather than the count -- a cluster of beads is still beads. A mark with a
    quarter of its outline made of straight runs reads as *stuff*: a flake off a
    floor, a grain, a chip.

    Not a clean sweep of chips, because that loses the one thing the discs were
    for. A lobe of one is a rounded shoulder, and shoulders are what stop the
    silhouette from reading as a shard of glass: too many corners and the mark
    is a heap of debris, which is a different effect and a louder one.
    """
    PUFF_CHIP_SIDES = (4, 6)
    """How many edges a chip has, as a range.

    Four is a flake, six is a pebble, and both are read as matter at three
    pixels across. A triangle is not: at that size its apex is a single pixel
    standing proud of everything else, and a sheet with a fringe of single
    pixels standing off it reads as sparkle -- which is the parry's job, and
    the dust got a grain family precisely so it would not have to do it here.
    """
    PUFF_CHIP_TURN = 1.0
    """How far a chip's heading is drawn from, as a share of a full turn.

    At 1.0 two chips land on the same orientation about one time in four, which
    is enough coincidence to read as a coincidence. Lower it and the chips
    start agreeing with each other, and past about a third they read as strata
    rather than as grit -- layered, crystalline, a different material. Worth
    knowing the dial is there before reaching for it.
    """
    PUFF_CHIP_GROW = 1.4
    """How much bigger a chip is drawn than the disc it replaces, by radius.

    Not a fudge: a regular polygon covers noticeably less than the circle
    inscribed in the same radius, and the share the chips take is drawn on the
    same numbers as the discs. A quadrilateral is 0.64 of its disc's area and a
    hexagon 0.83, so swapping part for part at one radius quietly *thins* the
    band -- and thinning it is not the same change as squaring it. The sheet
    stops being a mass and becomes a row of separate specks, which is the one
    thing the two strata exist to prevent.

    It is the difference between a sheet of dust and a heap of gravel, and it
    has to be this number rather than a bigger entry in the share ranges,
    because the two kinds are drawn from the same draw.
    """
    PUFF_SQUASH = 0.72
    """How flat the first step is, as a share of the sheet's own height.

    Dust leaves the ground, it does not leave a sphere. A sheet that starts low
    and tight and opens as it rises is the read; one that starts at full height
    is a cloud that was already hanging when it was kicked.

    Close to one, where the squashing used to be deep. The band is already
    built wide and shallow, so flattening it again on top of that only crushed
    the lobes into each other and closed the notches the silhouette depends on.
    """
    PUFF_TINT = (-0.18, 0.12)
    """The per-puff body shift, so a fan is not four identical sheets."""
    PUFF_VARIANTS = 4
    """How many distinct silhouettes a fan draws from.

    One per slot in the fan, so the members of a fan differ in *shape* as well
    as in tone and size. A tone and a size are both global properties of a
    mark, and a fan that varies only those reads as one shape stamped four
    times at four zoom levels -- which is a spinner, and a spinner is the other
    half of the thing that read as a child drawing.

    Kept equal to the tone count on purpose: the two are then indexed together
    and a puff's tone and shape can never pair up twice, so no two members of a
    fan match on either.
    """
    TTL_JITTER = (0.7, 1.0)
    """Per-puff life, as a share of ``TTL``.

    The fan used to share one TTL and die on the same frame, which read as a
    blink. Staggered, it dissolves -- the outer puffs, thrown hardest, are the
    ones that live longest.
    """
    SIZE_PROFILE = (0.8, 1.15, 0.9, 1.0)
    """A fixed rhythm of sizes around the fan, as shares of the base radius.

    Alternating big and small by index rather than leaving it to the jitter:
    a symmetric fan of equal clouds reads as a loading spinner, and the eye is
    far better at spotting a size pattern than it is at reading a random draw.
    Indexed by ``index % len`` so the profile wraps if ``COUNT`` ever stops
    matching it.

    Narrower than it was. A rhythm of ``0.7`` to ``1.25`` is a ratio of nearly
    two to one, and a fan of four puffs at two very different sizes is four
    objects rather than one event; the range is now just enough that the
    alternation is legible without the sizes competing.
    """


class DustGrain:
    """The loose grit thrown around a landing dust, and off a dash.

    This is the family that makes the puffs read as dust. A kick off a floor
    does not throw a handful of clouds and nothing else -- it throws a spray of
    small particles that travel much further than the mass does, arrive first,
    and are gone long before it, and a mark with no spray around it is a puff
    of smoke no matter how it is shaded.

    Three things make a grain a grain rather than a smaller puff. It is a
    handful of pixels rather than a shape, so it carries no silhouette to read.
    It is never opaque, because dust in the air is a haze and an opaque speck
    is a chip of stone. And it falls much faster than the mass it came from,
    since it has nothing holding it up.

    Kept in its own family and its own budget rather than appended to
    :class:`Dust`, so that a plane already full of marks sheds the grit
    instead of the landing. Losing the spray costs the effect a little of its
    read; losing the landing costs the game its feedback.
    """

    LANDING_COUNT = 14
    """Grains on a landing.

    More than there are sheets, and deliberately so: the grains are what the eye
    actually reads as motion, and they are cheap enough to be the majority of
    the event. Fourteen is under the family's budget alongside four sheets and
    the ground mark, so a hard landing spends what it is allowed to.
    """
    DASH_BURST_COUNT = 12
    DASH_TICK_COUNT = 4
    """Grains on the dash's shove, and on the puffs that extend the ribbon.

    Few on a tick. The ticks are laid one after another along 88px of path, so
    a tick that threw as much grit as the burst would fill the whole line of it
    and bury the ribbon that is the entire point of the trail.

    Up with the sheets, for the reading that a dash is meant to be the dustiest
    movement in the plane: the spray is what the eye reads as motion, so adding
    sheets without adding grit makes a heavier dash that has lost the part that
    was moving.

    The tick count is where the budget went, not the burst's. A dash asks
    twelve on its shove and four on each of the two ribbons after it -- twenty,
    which is why ``dust_grain`` is thirty-four and not the twenty-four it was:
    the cap has to hold a dash and a landing together, because landing out of a
    dash fires both on one tick and the landing is the one that wins. Fourteen
    and twenty are thirty-four. At five ticks it would be thirty-six, which is
    one over, and one over is the difference between the landing's spray
    surviving and being refused whole.
    """
    SIDE_SPREAD = 1.6
    """How far either side of the fighter the spray is laid, in half-widths.

    Wider than the sheets' own footprint, and for the same reason they are laid
    across the feet rather than at the middle of them: the plane is painted
    under the moving layer, and every grain thrown from inside a forty-wide
    body is a grain nobody sees.

    Up from 1.3 for the dash's sake, and it is a shared number rather than a
    dash-only one, so the landing's spray widens with it. That is the cheaper
    trade: a wider spray on a landing is more grit around a mark the player is
    already looking at, and the alternative is a third number whose only
    difference is which event reads it.
    """
    SIZE_RANGE = (1, 3)
    """A grain's side, in whole pixels.

    One to three, and the ceiling is what stops the field from reading as
    gravel: a four-pixel speck has its own silhouette, and a cloud of shapes
    with their own silhouettes is a swarm of objects rather than a spray.
    """
    SIZE_MIX = 1.0
    """The share of ``SIZE_RANGE`` that one emission sweeps, across its grains.

    Swept rather than sampled, and over the whole range at 1.0, so a landing
    has its coarse grains and its fine ones and both are on screen at once. A
    uniform draw from ``(1, 3)`` lands mostly on two, because that is where the
    numbers are, and a field of two-pixel specks is dotted.

    Below 1.0 it stops short of the coarsest size rather than thinning the
    sweep, which is the knob to reach for if the three-pixel grains ever read as
    gravel: a landing wants some, a dash laid along a path does not.
    """
    TONE_MIX = (-0.4, 0.55)
    """The per-grain tone shift, off ``FXColors.dust_grain``.

    Both ways, unlike every other tint in the plane, and further than any of
    them. A spray of one grey is a cut-out, and the variation has to go dark
    as well as bright or the field still reads as a printed pattern. The top of
    the range is where it gets a grain brighter than the sheet it came from,
    which is the one thing that makes a one-pixel speck legible against a tiled
    floor at all: the bright ones carry the read and the dark ones carry the
    texture, and a spray of mid-tones carries neither.
    """
    GRAVITY = 620.0
    """Downward, and much the strongest on the plane.

    A grain has no lift behind it. The landing puff gets away with an upward
    ``RISE`` used as its gravity because a cloud still has air under it; a
    speck thrown to the same height and stopped there hangs, and hanging specks
    around a landing read as a swarm of insects.
    """
    DRAG = 2.5
    THROW = 34.0
    """Sideways, the distance a grain is flung from the spot that threw it.

    Well past the sheet's own spread -- about twice it, which is what the
    grain's own drag works out to over a fling. A grain that stays inside the
    sheet it came from is invisible: it is drawn in a tone close to the mass,
    at a size of two pixels, under a sheet of the same thing. The whole of the
    effect is that the spray lands *outside* the cloud.

    Capped near seventy rather than the hundred and fifty it started at. The
    drag is what keeps it honest, and the drag has not changed while the sheet
    has: a grain crossing a hundred and sixty pixels on a hard landing is dirt
    already on the screen rather than part of the kick.
    """
    RISE = (30.0, 130.0)
    """Upward, as a range.

    Wider than the sheet's own kick on purpose, and higher at the top, so a few
    grains go further and higher than the mass and the ones that arrive first
    are the ones that came from furthest out. The opposite of the sheet's
    arrangement, and the reason the two together read as one kick rather than
    as a cloud with dots on it.

    Both figures are the grain's own, and both come back down: ``GRAVITY`` is
    more than four times what the sheet gets, so a grain thrown to the top of
    the range peaks a little under fourteen pixels up and is falling again well
    inside its life. A grain that hangs is a mote of smoke.
    """
    BACK_SHARE = 0.35
    """The share of grains thrown backward, against the direction of travel.

    A minority, and for a landing it is against the *facing*, which is the only
    direction it has. A spray thrown against a dash would cross the fighter's
    own path, and the FX plane is painted under the moving layer precisely so
    that a fighter is never behind his own dust -- so the backward share is
    kept small and the rest go sideways, which is where a boot actually throws
    the floor away.
    """
    TTL = 0.22
    """How long a grain lives, and well inside the sheet's.

    The spray is the punctuation and the sheet is the sentence. A grain that
    outlived the mass it was thrown with left specks hanging in clear air after
    the landing had finished reading, which is worse than not throwing it at
    all -- and it is also why ``GRAVITY`` gets to be this strong: a grain's
    whole arc has to fit inside a fifth of a second, and the only way to land
    one in that time is to bring it down hard.
    """
    FADE_IN = 0.02
    ALPHA_STEPS = 4
    MAX_ALPHA = 165
    """The opacity ladder a grain fades through, and how opaque it gets.

    Four levels against the plane's eight, and that is a coarser fade rather
    than a fainter one -- the top of every ladder is full opacity, so the
    ceiling is a separate number and it is the number that matters. A grain
    peaks at 165, two thirds of solid, and the shortfall is what the eye reads
    as air. At 255 a speck is a chip of stone thrown at the screen, which is a
    heavier object than anything a landing throws.
    """


class DashDust:
    """The dust a dash throws out of the fighter's trailing edge.

    Two emissions rather than one. A burst is thrown on the tick the dash
    starts, and a small puff follows on a cadence until the dash ends, so the
    mark is a continuous ribbon along the path instead of one cloud sitting
    where the fighter used to be. The dash is short -- ``Physics.DASH_DURATION``
    is 0.08s -- and the fighter is 88px away by the time it ends, so the trail
    has already been left behind before the first puff reaches its peak.

    Separate from :class:`Dust` because it is a different job. Landing dust
    answers "how hard was that", is scaled by the fall speed, and lives long
    enough to be read at the fighter's feet. This answers "that was a burst of
    movement", ignores the landing entirely, and is thrown backwards.

    Painted without an ink rim, in two tones, on the argument
    :class:`ShieldArcParticle` makes for the block: at this size a mid-grey
    outline turns a mark into a drawn shape with nothing light about it, and a
    single flat tone is a blob. The separation is carried by the lit edge
    instead, laid along the top of the cloud.

    Which is the same change the landing sheet made, for the same reason. The
    trail used to carry a disc of highlight set into its own top-left, and a
    burst of twelve of those under a stretched rectangle is a picture of a
    cartoon skid. A one-pixel rim along the top of a small irregular band is
    the same read with none of the drawing convention in it.
    """

    SPAWN_EVERY = 0.02
    """Seconds between the puffs laid along the path.

    Tied to ``Afterimage.SPAWN_EVERY`` (0.012s) closely enough that the two
    marks read as one movement rather than as a trail with a second, faster
    trail inside it.
    """
    BURST_COUNT = 7
    """Puffs on the dash's first tick: the shove off the floor.

    The fan is laid out across the fighter's width for the same reason the
    landing fan's is: the trail is painted under the moving plane, and a
    plume thrown from the middle of the body spends the dash behind him.

    Up from five, on the reading that the dash should be the dustiest thing in
    the plane and the gap between it and the trail it replaced was the whole
    complaint. Then again, from six, when the dash was asked for more volume.

    The burst is capped by the family's budget before the ribbon is, and the
    ribbon is the part a truncated trail cannot survive, so this is the number
    that gives way first. Seven plus two ribbons of four is fifteen against the
    family's twenty.
    """
    TICK_COUNT = 4
    """Puffs on every later tick of the dash, filling in the ribbon.

    Two rather than one because ``SPAWN_EVERY`` is not a divisor of the frame
    time: a single puff per emission leaves visible gaps along a path the
    fighter crossed at 1100 px/s.

    Three rather than two for the same reason the burst grew, and the tick is
    where the extra one is worth most: the burst is over in a frame and the
    ticks are what the player watches evaporate down the path behind him. Then
    four, for the same asking.

    ``SPAWN_EVERY`` puts four emission slots in ``DASH_DURATION``, so the most a
    dash can ever spend is a burst and three ribbons -- nineteen puffs at any
    frame rate above ninety hertz, and fifteen at the sixty this was measured on.
    Both are inside the family's twenty; see the budget table for why the
    headroom is one puff rather than five.
    """
    BURST_TTL = 0.7
    TICK_TTL = 0.5
    """How long a puff lives.

    Both outlast the dash itself, which is the point: the trail has to still
    be evaporating after the fighter has left it, or it reads as debris
    rather than as the movement that threw it. The burst lingers longest
    because it is the biggest and was thrown hardest.

    These are the ceiling on how high the trail can go, and they were raised
    rather than the kicks left alone. A puff kicked at ``v0`` against
    ``GRAVITY`` turns over after ``v0 / GRAVITY`` seconds, so the highest a
    mark may be thrown is ``GRAVITY * TTL`` -- and a trail that is allowed to
    propagate upward has to be allowed to come back down inside its own life,
    or it dies mid-climb and reads as smoke off a fire. Raising the kicks past
    what these allowed is the exact failure ``test_the_trail_plume_turns_over``
    was written to catch; raising the life is what buys the height honestly.

    So the burst's ceiling went from seventy-two to eighty-four and the tick's
    from forty-eight to sixty, and the kicks went to eighty and fifty-six under
    them -- seven pixels of headroom on each, which is the frame or two of
    settling the turn-over needs before the fade starts.
    """
    BURST_RADIUS = 8.0
    TICK_RADIUS = 5.0
    """Puff radius, as shares of the painted sheet.

    Down from ``12.0`` and ``6.5``, for the reason the landing fan's were cut
    and not for any of the local ones below: the trail is drawn under the
    moving plane, and a burst twice the fighter's width is not a mark he went
    through, it is a screen he is behind. It still has to clear the body it is
    behind -- a cloud narrower than the fighter is spent before he has moved
    past it -- which is why the burst is still the larger of the two rather
    than merely the first of them.

    Down because the sheet is now a band of small parts rather than a ball
    with lobes on it: the same nominal reach covers far more of the fighter's
    width than it did, and holding the old numbers would have doubled the mark
    in the only frame where it is the whole movement.
    """
    FADE_IN = 0.04
    """A fifth of the block's, because the trail is late if it eases in.

    The fighter crosses most of the ribbon in the first 0.08s; a slow ramp
    means the dust is still fading up where he already isn't.
    """
    GRAVITY = 120.0
    """Downward, so a kicked puff rises and comes back down.

    The landing puff gets away with an upward ``RISE`` used as its gravity,
    which accelerates it off the floor for its whole life. A trail cannot: it
    is a mark that has to stay along the ground the fighter left, and dust
    that is still climbing half a second later reads as smoke rising off the
    spot rather than as the trail of someone who went past it.
    """
    KICK = (30.0, 80.0)
    """The height each burst puff is kicked to, as a range rather than a cap.

    A range, so the burst stacks into a plume with lobes at different heights
    instead of a row of clouds all leaving the floor at the same speed -- and
    with the dash asked to propagate further upward, the *width* of the range is
    as much of the answer as its top: a plume whose six lobes all leave at
    thirty is a flat sheet thrown a long way, while thirty to eighty stacks
    them over half the fighter's height and reads as volume.

    The top of the range is not a taste, it is the ceiling: a puff turns over at
    ``kick / GRAVITY`` seconds, so it cannot be thrown above ``GRAVITY *
    BURST_TTL`` -- eighty-four on these numbers -- without the tallest of them
    still climbing when it fades, which reads as smoke off a fire rather than as
    dust off a floor. Eighty puts the turn-over at 0.667s against a 0.7s life,
    so the arc completes and the plume is already coming back down as it goes.

    That top was seventy when the life was 0.6s, and it was pulled down from
    eighty-eight once before that for dying mid-climb. It is back up to eighty,
    and the difference is that the life moved rather than the reading changing:
    at a 0.7s life eighty settles with two frames to spare, where eighty-eight
    would not have at any life this plane ships. See ``BURST_TTL``.
    """
    TICK_KICK = 56.0
    """The height the ribbon's puffs are kicked to, uniformly.

    This is the one number the ribbon is really made of: the burst is a shove the
    player has already read off the fighter, while the ticks are the marks
    lying along 88px of path, and it is those that were reading as a skid
    painted on the floor rather than as dust in the air.

    Up from thirty-four, twice: once to lift the ribbon clear of the tiles it is
    drawn over, and once more when the trail was asked to propagate further
    upward. The fighter is at 1100 px/s and the marks are behind him, so a
    ribbon sitting in the same two pixels of floor for its whole life reads as
    paint rather than as dust.

    The peak is ``KICK ** 2 / (2 * GRAVITY)``, so fifty-six is a shade under
    thirteen pixels against the old five and then nine. Still below the burst's
    twenty-seven, which is the arrangement that reads as one movement: a shove
    that throws high and a path it leaves lying lower behind.

    Uniform rather than a range, because the ticks are laid one after another
    along a line, where a height spread reads as a mess rather than as a
    ribbon. Its own ceiling is the tick's and it is tighter than the burst's --
    a tick lives ``TICK_TTL`` against ``BURST_TTL``, so the same formula caps it
    at sixty. Fifty-six is four under that, which is the frame or two the
    turn-over needs; see ``test_the_trail_plume_turns_over_before_it_fades``.
    """
    THROW = 150.0
    """How hard the burst is shoved backwards, against the dash direction.

    The only thing that makes the trail read as trailing. Forward, or without
    a throw, the cloud stays under the fighter and looks like dust he is
    standing in.
    """
    TICK_THROW = 20.0
    """How hard the puffs that extend the ribbon are shoved.

    A seventh of the burst's, and the difference between a trail and a clump.
    A tick is laid where the fighter just was and left there; thrown as hard
    as the burst it is dragged back into the cloud that started it, and
    instead of a ribbon along 88px of path there is one mass at the start of
    it.
    """
    SPREAD = 40.0
    """Sideways fan of the burst, so it is a plume and not a line of clouds.

    Narrower than the landing fan's, because the burst's puffs are twice the
    size: spread them as far as a fan of four small ones and the members of the
    plume are far enough apart to read as separate clouds in a row rather than
    as one ragged mass.

    Up from thirty, with the counts, because a dash is meant to be the dustiest
    thing in the plane and this is the number that says how wide. It fans the
    burst and the ticks both -- the ticks through the same ``lateral`` term --
    and it is the width the whole trail is laid in, so raising it is what makes
    a dash read as more scattered than the comb of footsteps behind it rather
    than merely faster than them.
    """
    SPREAD_JITTER = 38.0
    """Random share of ``SPREAD``, per puff.

    Slightly above the share it was at relative to the spread, so a widened
    trail does not come out as a neat fan: the jitter is what keeps six puffs
    from reading as six identical marks at six tidy offsets. Deliberately below
    ``SPREAD`` itself, which is what stops the outermost member from landing
    further out than the fan says it does.
    """
    BACK_OFFSET = 0.4
    """Where along the body the trail is laid, as a fraction of its width.

    At the trailing edge rather than the centre, so the puffs are left
    behind on the way out instead of being carried forward by the fighter
    for the first frame of the dash.
    """

    STEPS = 4
    BUCKETS = (4, 6, 9)
    """The radii a puff is painted at, smallest first.

    Discrete for the reason the landing ladder is: a continuous radius means
    a surface per particle, and a dash lays a ribbon of them.
    """
    GROWTH = 0.3
    """How much further the sheet reaches at each step, as a share of the
    radius it started at. The last step is drawn at ``1 + growth * (steps-1)``.

    Steeper than the landing sheet's, because a trail is the one mark in the
    plane that has to keep reading after the fighter has left it, and a cloud
    that stays the size it was born leaves the tail looking cut off.

    Up from 0.25 when the dash was asked for more volume, and this is where that
    came from rather than from a bigger base radius. Two reasons: the ladder is
    keyed on *discrete* radii, so a larger ``TICK_RADIUS`` would buy one whole
    bucket step and no more, whereas this is continuous; and the base is shared
    with the mark at the moment it is born -- the frame the fighter has already
    dashed past -- so raising it puts a bigger cloud where nobody is looking,
    while growing it puts the volume at the peak of the puff, which is where the
    trail is what the player is reading.

    Stopped at 0.30 rather than the 0.40 it was set to first, and the reason is
    measured rather than felt: the ladder's last step goes from 1.75x the base
    radius to 1.9x here and to 2.2x there, and because the ladder scales both
    axes the extra volume arrives as width too. Averaged over five seeds, the
    plume's top off the floor goes 32.5px at the old setting, 38.6px here and
    40.6px at 0.40 -- while the trail's span across the screen goes 2.34x the
    fighter's width, 2.49x and 2.64x. The last two steps of that buy four
    percent of height for six percent of width.

    It was 0.35 once, pulled down to 0.25 when the base radius came down, and is
    back between the two. The frame the smaller base was chosen to fix is still
    safe: the trail is laid at the trailing edge and thrown backwards, so what
    this widens is a mark the fighter is leaving, not one he is in.
    """
    STEP_OPENS = 0.5
    """The share of the life the trail takes to open over."""
    MOTES = 11
    """How many lobes the sheet is built from.

    More than the landing sheet's, at a smaller radius: at the burst's size the
    lobes are the only thing giving the mark an edge at all, and a rim light
    around four large discs is a rim light around four discs.
    """
    BASE_SHARE = (0.24, 0.32)
    """The lower band's lobes, as shares of the radius, across a range.

    The landing sheet's arrangement, for the landing sheet's reason: the band
    has to be one connected mass, so these are the lobes large and close
    enough to touch, and the fringe above them is free to scatter.
    """
    TOP_SHARE = (0.1, 0.15)
    """The fringe's lobes, as shares of the radius, across a range.

    Finer than the landing sheet's, and the reason is the size: a fringe of
    lobes that read as grit at the landing sheet's radius is a fringe of
    separate specks at the burst's, and the burst is the one mark on screen at
    the instant of the dash. It has to read as a mass first and as dust second.
    """
    MOTE_SPREAD = 0.98
    """How far the band reaches either side of its centre, as a share of the radius.

    A shade wider than the landing sheet's, and shallower for it: the trail is
    thrown rather than kicked and hangs on open air, so there is nothing under
    it to squat into, and a band that hugged its own baseline read as grounded
    -- as a puff that had landed rather than as one being left behind.
    """
    MOTE_RISE = (0.1, 0.66)
    """How far above the band's floor the fringe sits, as a share of the radius.

    Nearly twice the landing sheet's reach and about one and a half times its
    spread, for the same reason the fringe is shorter: the trail hangs on open
    air, so its mark has to stand on its own rather than read as depth, and
    the only thing available for that is height.
    """
    MOTE_BASELINE = 0.3
    """Where the band's own floor sits, as a share of the radius below centre.

    Kept on the centre rather than below it, where the landing sheet's is
    pushed under. The trail is thrown rather than kicked, and the weight of a
    thrown thing is not at the bottom -- so the band's mass stays around the
    axis and the growth over the ladder is the only thing that settles it.
    """
    MOTE_EVERY = 3
    """Every ``n``-th fringe lobe is drawn at the top of ``TOP_SHARE`` instead."""
    CHIP_SHARE = 0.78
    """The share of the trail sheet's lobes drawn as chips rather than discs.

    Higher than the landing sheet's, for the reason the trail is a different
    mark: it is read as it is left behind, at a distance, along 88px of path,
    and a silhouette made entirely of arcs holds together at that range where
    the notches between chips do not. Finer edges read as noise from far off,
    so the trail leans harder on the parts of the outline that survive being
    small.
    """
    CHIP_SIDES = (4, 6)
    """How many edges a chip has, as a range.

    The landing sheet's, and for the same reason: a triangle at this radius is
    a single pixel standing proud, and the trail is the mark that cannot afford
    a sparkle along its whole length.
    """
    CHIP_TURN = 1.0
    """How far a chip's heading is drawn from, as a share of a full turn.

    A full turn here for the landing sheet's reason, and with more to lose from
    it: the trail's chips are what keep the ribbon from looking like a row of
    beads, and agreeing orientations would put the same bead back.
    """
    CHIP_GROW = 1.35
    """How much bigger a chip is drawn than the disc it replaces, by radius.

    The landing sheet's arithmetic, with half a percent less on it because the
    trail's chips are larger to begin with and the area a polygon is short by
    grows with the number of sides, not with the radius.
    """
    SQUASH = 0.66
    """How flat the first step is, as a share of the sheet's own height.

    Above the landing sheet's, because the band is not already wide and shallow
    by the amount the landing one is, so the first step is where the flatness
    is actually applied.
    """
    TINT = (-0.12, 0.18)
    """The per-puff body shift, so a ribbon is not a row of identical sheets.

    Narrower and brighter than the landing fan's: the trail is a smaller set
    of marks read faster, and a wide tone range across it reads as noise
    rather than as variety.
    """
    VARIANTS = 5
    """How many distinct silhouettes an emission draws from.

    One per slot in the burst, so a plume is five different small shapes rather
    than one shape at five sizes. The tick's two are drawn from the first two,
    which is deliberate: a tick is laid next to its neighbour, and two ticks
    that did not match would read as two events on one path.
    """
    TTL_STAGGER = (0.75, 1.0)
    """Per-puff life, as a share of the emission's ``BURST_TTL`` or
    ``TICK_TTL``, spread by how far out the puff sits.

    The outer puffs of a plume are thrown the furthest sideways, so they are
    the ones that should last. Without the spread the emission dies on a
    single frame and the trail blinks.
    """
    RADIUS_JITTER = 1.5
    """Per-puff radius, so a burst is not five identical sheets.

    Small on purpose: the burst and the ticks already differ by most of a
    factor of two, and jitter on top of that reads as noise rather than as a
    plume with a shape.
    """


class FootstepTier(NamedTuple):
    """One locomotion tier's dust: how far between steps, and how scattered.

    Two numbers and no more, because those are the only two things a footstep
    has that differ between a walk and a run. The mark's own size cannot carry
    the difference -- the ladder is drawn at the nearest of its discrete radii,
    so every request under the second bucket is the same sheet -- and its height
    should not: a foot is a foot, and a run's lands no higher than a walk's.

    Which leaves cadence and spread, and those two are what the eye reads as
    gait. A loose comb at a run's pace and a tight one at a walk's is a
    difference in *how the fighter moves*, which is the claim the effect makes;
    the same difference in how big the puffs are would only be a difference in
    how loud they are.
    """

    step_distance: float
    """Pixels of ground covered between two steps in this tier.

    Paced by distance rather than by time so the marks come out evenly spaced
    along the ground. A time-paced comb would space them by the stride instead,
    which puts the slow tiers' marks closer together on the floor and reads as
    clustering rather than as walking.
    """
    spread: float
    """This tier's share of ``FootstepDust.SPREAD``.

    A scale rather than a number so the base stays the one place the mark's
    width is written down and the tiers say how much of it they want. Below one
    the pair is close to a single mark under the heel, which is what a walking
    shuffle should look like; above one the two halves of a step separate and
    the comb stops reading as one line down the middle of a path.
    """


class FootstepDust:
    """The dust a fighter's feet throw off while it walks, runs or rolls.

    The third dust mark in the plane, and the only one that is neither an event
    nor a movement: landing dust answers "how hard was that" and the dash trail
    answers "that was a shove", while this one answers the question the other
    two leave open, which is whether the fighter is moving at all. Before it,
    a fighter at full run along a floor left nothing in the plane -- the dash
    got a trail and a slow walk got nothing, so the one movement that is
    continuous looked like the one movement that displaces nothing.

    **The cadence is per tier, and the tiers are read by name.** :data:`TIER`
    holds one row per ground state -- ``walk`` and ``run`` -- and the absence of
    a row is the instruction, which is how ``walk_slow`` comes to throw nothing
    at all. That is the reading the effect wants: a fighter shuffling under a
    raised guard is holding still as far as the ground is concerned, and
    marking him every stride says he is travelling when he is not.

    Reading the state name rather than the speed reverses the obvious version,
    and deliberately. ``resolve_locomotion_state`` already makes this decision,
    with hysteresis so it does not flicker while acceleration crosses a
    boundary; re-deriving it from ``|velocity.x|`` would duplicate that
    classifier and put the flicker back -- and at this cadence a flicker is a
    scuff appearing and vanishing under a fighter who is barely moving. "Silent
    while ``walk_slow``" is also a claim about what the state *means* rather
    than a threshold, because a fighter easing out of a run passes through the
    same speeds without having become a guarded one.

    So :data:`TIER` is keyed on ``PlayerState`` values, and nothing here imports
    the state machine to prove it. ``test_fx_invariants`` checks every key
    against the enum instead, which is what keeps a string key from quietly
    going stale.

    Anything *outside* the table -- an enemy patrolling, say -- gets
    :data:`DEFAULT_TIER`, which is the run row. Its speed is paced by distance
    like everyone else's, so a patrolling enemy at a third of its top speed lays
    a third as many steps and nothing about it is a special case.

    ``MIN_STEP_EVERY`` is the ceiling on all of this, and it is not optional. At
    ``Physics.PLAYER_SPEED`` the run row alone asks for a step every 0.04s, and
    twenty-five marks a second along a fighter's own path is the dash's ribbon,
    drawn small and in the dash's own lane. The floor is what keeps the effect a
    footstep -- a threshold below which the plane stops spending, not above which
    it spends more. It is what puts the run's spacing at thirty pixels rather
    than the fourteen it asks for, and the run is still the fastest comb in the
    plane at a little under three times the walk's rate.

    The mark sits behind the trailing foot rather than under the body, for the
    reason ``Dust.FOOT_SPREAD`` gives for the landing fan: this plane is
    painted *under* the moving layer, so a mark thrown from inside a
    forty-eight-pixel fighter spends its first third of life invisible behind
    him. A step is born behind the heel and reads as something he left.
    """

    TIER: dict[str, FootstepTier] = {
        "walk": FootstepTier(40.0, 0.6),
        "run": FootstepTier(14.0, 1.15),
    }
    """The ground tiers that mark the floor, keyed on ``PlayerState`` values.

    See :data:`SILENT` for the one that does not, and the class docstring for why
    the tiers are read by name rather than by speed.
    """
    SILENT: frozenset[str] = frozenset({"walk_slow"})
    """The ground tiers that deliberately leave no dust at all.

    Named rather than left as an absence, because the two cases are different
    and the difference is the whole reason this effect reads as gait. A tier
    absent from :data:`TIER` *and* absent from here is not a ground tier -- an
    enemy patrolling, a test double with no state machine -- and it gets
    :data:`DEFAULT_TIER` like anything else that is merely moving. Letting
    "not in the table" mean both things is how an enemy chasing you ends up
    marking the floor at a walker's cadence.

    ``walk_slow`` is in it for the reason in the class docstring: a fighter
    shuffling under a raised guard is holding still as far as the ground is
    concerned, and marking him every stride says he is travelling when he is
    not. It is also the tier ``Guard.MOVE_MULT`` (0.35) drops to, so it is the
    one that shows up on every block in the game and the one that must not turn
    a guard into a running start.
    """
    DEFAULT_TIER = FootstepTier(14.0, 1.15)
    """What a fighter that is not in :data:`TIER` gets: the run row.

    The numbers are repeated rather than referenced so a reader who finds one
    row does not have to follow a name to find the other. The two have to stay
    equal, and
    ``test_the_default_footstep_tier_is_the_run_row`` holds them together.
    """
    MIN_STEP_EVERY = 0.085
    """The shortest interval two steps may have, in seconds.

    The ceiling on the cadence, and the number that keeps a run from turning
    into a trail. At ``Physics.PLAYER_SPEED`` with the run row's fourteen pixels
    alone, a fighter asks for a step every 0.04s -- twenty-five a second -- and
    twenty-five marks along a fighter's own path is the dash's ribbon again,
    drawn small, which is the one thing that would make the dash stop being the
    fastest thing in the plane that leaves a mark.

    Eighty-five milliseconds is about twelve steps a second, which is faster
    than the run sprite sheet changes leg (``Animation.RUN_FRAME_DURATION`` is
    0.08) -- close enough that the marks land on the leg they belong to
    without the floor ever being the thing the eye notices. Against the walk
    row's forty pixels it leaves the run a little under three times the rate,
    which is the difference the eye actually reads as gait.
    """
    MIN_SPEED = 20.0
    """Below this ground speed, a fighter leaves nothing at all.

    The plane's other FX ignore standing still, and so does this: a mark per
    frame of the friction settle would be a puff that never stops appearing
    under a fighter who has already stopped. Above ``Locomotion.
    STOP_SPEED_PX_S`` (0.5) by a wide margin, so a fighter easing out of a run
    keeps marking the ground until it has genuinely stopped, rather than
    stopping dead at the last frame where the difference is invisible.
    """
    COUNT = 2
    """Puffs in one step.

    Two rather than one so the mark has a width the eye can hold as a foot,
    and the same count as the dash trail's tick for the reason that one has:
    two small parts side by side read as a scuff, and one reads as a speck the
    fighter happened to pass over.
    """
    RADIUS = 4.0
    """Per-puff radius, as a share of the painted sheet.

    This is a *request*, not a size: the trail's ladder is keyed on the discrete
    radii in ``DashDust.BUCKETS`` and drawn at the entry nearest the request, so
    everything from nothing up to ``BUCKETS[1]`` comes out as the same sheet.
    Four is inside that first bucket, which is the point of the number -- the
    footstep draws the smallest mark the plane can draw and there is nothing
    below it to go to.

    Which also means a size knob cannot be added here: any radius under six
    produces byte-identical pixels, so a mark scaled by ground speed would move
    a number and not the screen. The cadence is what says how fast the fighter
    is going, and it is already doing it: the same mark, laid tighter and
    tighter as he speeds up.
    """
    TTL = 0.3
    """How long a step lives.

    Shorter than ``DashDust.TICK_TTL`` (0.4) because this is the most frequent
    mark in the plane and the one with the least claim to being read: a step is
    punctuation between two positions, and a comb of them only reads as a comb
    while the fighter is between the ends of it. Held longer they stack up
    into the low haze that the distance pacing was meant to avoid.
    """
    FADE_IN = 0.03
    """A shade faster than the trail's.

    A step is born behind a fighter who is already leaving it, so the ramp has
    to beat him off the floor or the mark's whole readable life happens where
    he is not.
    """
    GRAINS = 3
    """Grit thrown with a step.

    Three rather than the trail tick's, and it is the ``dust_grain`` family
    either way, so they come out of a budget sized for spray. The spray is
    what makes a mark read as dust and not as a smudge, and this is the one
    effect in the plane where the mark is small enough that the sheet alone
    would carry the read -- a step is two puffs at radius four, which at this
    magnification is a smudge.
    """
    KICK = (14.0, 26.0)
    """The height each puff is kicked to, as a range.

    Well under ``DashDust.TICK_KICK`` (34) and the same shape as it: a range,
    so a step is not two clouds leaving the floor at exactly one speed. A foot
    does not throw dust a third of a fighter's height; the point of the mark is
    that the ground was disturbed, which reads at a couple of pixels of arc.
    """
    THROW = 26.0
    """How hard a puff is thrown against the direction of travel.

    A fifth of ``DashDust.THROW`` (150) and, like it, always against the
    direction: a step is the dust the heel pushed backwards, so throwing it
    forwards would put the mark ahead of the fighter instead of behind him.
    """
    SPREAD = 12.0
    """The sideways spread of the pair at one share, in px/s.

    Narrow, and narrower than ``DashDust.SPREAD`` because the pair is already
    laid at the heel: a step whose two halves fanned across half the fighter's
    width would be a landing's worth of motion at a walking pace.

    This is the base the tiers scale, not a fixed width -- a ``walk`` takes 0.65
    of it and a ``run`` takes 1.2, so the walk's pair is a single mark under the
    heel while the run's two halves separate. See :class:`FootstepTier`.
    """
    BACK_OFFSET = 0.35
    """Where along the fighter the mark is laid, as a share of his width.

    Behind the trailing edge rather than across the footprint the way
    ``Dust.FOOT_SPREAD`` lays a landing, because the landing has a fan to spread
    and a step has a pair: a landing is one event read as a spread, a step is
    a repeated event read as a comb, and a comb only reads as a comb if the
    marks come out in the same place along the body every time.
    """
    FOOT_ALTERNATE = 0.18
    """How far either side of the trailing edge each foot lays its step, as a
    share of his width.

    Alternating the depth between steps is what makes the comb read as two feet
    rather than as one mark stamped down the middle of a path, and it is free:
    the parity is the step counter the distance pacing already keeps, so there
    is no second clock to read.

    Small because the plane is magnified. On a forty-pixel fighter this puts the
    two lines seven pixels either side of where the trailing edge was -- a
    fifth of his width, which reads as two feet and no more. A half-width would
    have the marks striding across the fighter's own silhouette, and the mark is
    painted *under* it, so most of that would never be seen at all.
    """
    GRAVITY = 120.0
    """Downward, the trail's number and for the trail's reason.

    A step is a mark on the ground, so it has to be back on the ground before it
    is gone. With ``DashDust.GRAVITY`` the puff's whole arc is a few pixels and
    it settles inside its own life; the landing sheet's negative-gravity trick
    would send it drifting up for all three tenths of a second.
    """
    DRAG = 4.0
    """Horizontal drag, ``Dust.DRAG``'s number, and its reason.

    The mark is laid at the heel and thrown backwards; drag is what stops it
    from becoming a streak travelling along the fighter's own path.
    """
    RADIUS_JITTER = 1.0
    """Per-puff radius, so a step is not two identical puffs.

    Below ``DashDust.RADIUS_JITTER`` (1.5) on a smaller base radius, for the
    reason the trail cut its own: the two halves of a step are two pixels apart,
    and half a factor of two of jitter between them reads as two events rather
    than as one scuff.
    """
    TINT = (-0.08, 0.12)
    """The per-puff body shift, so a comb is not a row of identical sheets.

    Narrower and dimmer than ``DashDust.TINT`` (-0.12, 0.18), and less to make
    a stand: there are far more steps on screen at once than puffs in a trail,
    so the tone range is spread over more marks and each step contributes less
    of the sum.
    """
    TONES = 4
    """How many discrete tones that range is drawn in, and so how many ladders.

    Not decoration: the ladder is keyed on the tone it is handed, rounded to
    three places, so a *continuously* sampled tone misses the cache on every
    spawn and paints four surfaces to replace one. This number is the ceiling on
    that. It was a random draw per puff before, and the cost was not the misses
    but the misses forever: sixty seconds of running built 383 ladders, and the
    p95 of the emitter went to 828us -- a fifth of a frame, on one tick, over and
    over, for as long as the game was open.

    Four because the whole reachable grid is one radius bucket times this times
    the two silhouettes a two-puff step draws, so the footstep can never exceed
    eight cached ladders however long it runs. That is the number
    ``test_a_footstep_cannot_grow_the_ladder_cache`` holds it to.
    """


class FxDecal:
    """The mark a hard landing leaves on the floor."""

    RADIUS = 22.0
    TTL = 0.28
    FADE_IN = 0.05
    MARGIN = 6
    RING_STEPS = 3
    RING_GROWTH = 0.55
    RING_THICKNESS = 2.0
    RING_SQUASH = 0.34
    """How flat the mark sits, as a share of its own width. A circle on the
    ground reads as a disc floating on it; squashed, it reads as a mark the
    floor made."""
    RING_STEP_OPENS = 0.7


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
    SHARD_SEEDS = 8
    """How many distinct layouts the ring can come apart in.

    The bound, and it is the whole of the optimisation. ``_shatter_step`` is a
    pure function of its progress, its seed and the side the guard was hit on --
    nothing else about it varies per spawn -- so the geometry is worth painting
    once per *layout* rather than once per break. It was seeded from
    ``_fx_rng.randrange(1 << 16)`` per spawn, which made every break 65 536
    layouts wide, and that is the whole reason the plane's most expensive effect
    could not be painted twice: 81 arc strokes per step, three steps, measured at
    1.14 ms on a frame whose budget is 16.7 ms.

    Eight is not a guess about taste. The fragments are visible for
    ``SHARD_TTL``, which is 300 ms, twenty-seven of them move during it, and no
    two breaks land close enough together on screen for a repeat to be the one
    thing a player notices.

    Declared here rather than inside the particle because it is the size of the
    session's table, and belongs beside the other counts the geometry is built
    from.
    """


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
