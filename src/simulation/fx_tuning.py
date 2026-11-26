"""Tuning of the visual effects: dust, footsteps, guard rings, sweat, bodies.

Only the effect spawners and the particles read these, and the physics system
when it decides that a landing or a step raises dust. They are presentation:
nothing here changes the simulation.
"""

from typing import NamedTuple

from src.simulation.settings import Turn


class Dust:
    """Landing dust: a low sheet of grit thrown out of the feet on a hard landing.

    ``MIN_FALL_SPEED`` is read by the simulation too: it decides whether a
    landing is hard enough to throw dust at all. The rest is the look.

    The look is a low band of small parts -- a connected base and a scattered
    fringe, mostly chips rather than discs -- with a notched top edge and a
    one-pixel lit rim. A few large overlapping discs sum to one smooth oval,
    which reads as a bubble; many small parts read as material. The grains
    that make it read as dust rather than smoke are :class:`DustGrain`.
    """

    TTL = 0.4
    COUNT = 4
    MIN_FALL_SPEED = 500.0
    PUFF_RADIUS = 6.0
    RISE = 60.0
    """Gravity on a sheet, downward: kicked, it slows, turns over and settles.

    Upward, it would climb for its whole life and read as smoke off a fire.
    """
    DRAG = 4.0
    FADE_IN = 0.15
    FOOT_SPREAD = 0.3
    """Where along the fighter the fan is laid, as a share of his width.

    Across the footprint, not at its centre: the FX plane is painted under the
    fighters, and a puff born behind the body is hidden for the only part of
    its life anyone looks at.
    """
    # The horizontal spread of one puff, and its jitter.
    SPREAD = 55.0
    SPREAD_JITTER = 20.0
    RISE_RANGE = (12.0, 34.0)
    """The upward speed each sheet is kicked to; with ``RISE`` it is the arc's height."""
    RISE_ALTERNATE = 8.0
    """Extra kick for every other sheet, so the fan does not rise as one front.

    Small: it stacks on ``RISE_RANGE``.
    """
    RADIUS_JITTER = 1.5
    STRENGTH_PER_FALL = 1.2
    STRENGTH_RANGE = (0.7, 1.5)
    """How big the whole landing reads, by the fall speed that caused it.

    Capped so the hardest landing stays narrower than a fighter standing in it.
    """

    # --- the sheet: a ladder of steps per radius, shared by every puff ----------
    PUFF_STEPS = 4
    PUFF_BUCKETS = (3, 5, 7, 9, 12)
    """The radii a puff is painted at, smallest first.

    Discrete so each ladder is built once per session and shared; every bucket
    is a ladder kept alive, so an unreachable one is dead weight.
    """
    PUFF_GROWTH = 0.14
    """How much further the sheet reaches at each step, as a share of its radius.

    The last step is drawn at ``1 + growth * (steps-1)``. Small, so the sheet
    opens without swallowing the fighter.
    """
    PUFF_STEP_OPENS = 0.55
    """The share of the life the sheet takes to open; the rest it drifts and fades."""
    PUFF_MOTES = 11
    """How many parts the sheet is built from.

    Enough to notch the outline, few enough that each part is large enough to
    show a side; smaller parts turn back into little arcs.
    """
    PUFF_BASE_SHARE = (0.26, 0.36)
    """The lower band's parts, as shares of the radius.

    Large and close enough to touch, so the sheet is one mass. One shared
    distribution for base and fringe pulls the base apart into separate puffs.
    """
    PUFF_TOP_SHARE = (0.1, 0.16)
    """The fringe's parts, as shares of the radius: finer than the base, so the top tapers."""
    PUFF_MOTE_SPREAD = 0.94
    """How far the band reaches either side of its centre, as a share of the radius.

    The sheet is wide and shallow by its layout, not by squashing a disc.
    """
    PUFF_MOTE_RISE = (0.1, 0.45)
    """How far above the band's floor the fringe sits, as a share of the radius.

    Spread over several part heights, so the fringe overlaps the base in places
    and stands clear of it in others: that alternation is the notch.
    """
    PUFF_MOTE_BASELINE = 0.34
    """Where the band's floor sits below centre, as a share of the radius.

    Below, so the sheet's weight is in its lower two thirds: kicked dust does
    not hang.
    """
    PUFF_MOTE_EVERY = 3
    """Every ``n``-th fringe part is drawn at the top of ``PUFF_TOP_SHARE``.

    A stride rather than a draw, so every sheet gets the same few coarse grains.
    """
    PUFF_CHIP_SHARE = 0.72
    """The share of the sheet's parts drawn as chips rather than discs.

    Every arc on a silhouette reads as a bubble; straight runs read as matter.
    Not all chips, because a few rounded shoulders keep the mark from reading
    as a heap of shards.
    """
    PUFF_CHIP_SIDES = (4, 6)
    """How many edges a chip has.

    Four to six: at three pixels a triangle's apex is a lone bright pixel,
    which reads as sparkle.
    """
    PUFF_CHIP_TURN = 1.0
    """How far a chip's heading is drawn from, as a share of a full turn.

    Below about a third the chips align and read as strata.
    """
    PUFF_CHIP_GROW = 1.4
    """How much bigger a chip is drawn than the disc it replaces, by radius.

    A polygon covers less than its circle (0.64 for a square, 0.83 for a
    hexagon); without this the band thins into separate specks.
    """
    PUFF_SQUASH = 0.72
    """How flat the first step is, as a share of the sheet's height.

    Mild: the band is already shallow, and more squash closes the notches.
    """
    PUFF_TINT = (-0.18, 0.12)
    """The per-puff body shift, so a fan is not four identical sheets."""
    PUFF_VARIANTS = 4
    """How many distinct silhouettes a fan draws from.

    One per slot, and equal to the tone count, so no two members of a fan
    share a shape or a tone. A fan that varies only size reads as a spinner.
    """
    TTL_JITTER = (0.7, 1.0)
    """Per-puff life, as a share of ``TTL``, so the fan dissolves instead of blinking out."""
    SIZE_PROFILE = (0.8, 1.15, 0.9, 1.0)
    """A fixed rhythm of sizes around the fan, as shares of the base radius.

    A rhythm rather than jitter: equal clouds in a symmetric fan read as a
    loading spinner. Narrow, so the sizes alternate without competing.
    Indexed by ``index % len``.
    """


class DustGrain:
    """The loose grit thrown around a landing, a dash and a step.

    What makes the sheets read as dust: a kick throws small particles that go
    further than the mass, arrive first and are gone before it. A grain is a
    few pixels with no silhouette, never opaque, and falls fast.

    Its own family and budget, so a full plane sheds the grit before the
    landing it belongs to.
    """

    LANDING_COUNT = 14
    """Grains on a landing: the majority of the event, since they carry the motion."""
    DASH_BURST_COUNT = 12
    DASH_TICK_COUNT = 4
    """Grains on the dash's shove, and on each puff that extends its ribbon.

    The budget is sized for a dash and a landing on one tick: twelve plus two
    ribbons of four, plus the landing's fourteen, is the family's thirty-four.
    """
    SIDE_SPREAD = 1.6
    """How far either side of the fighter the spray is laid, in half-widths.

    Wider than the body, since grains thrown from inside it are drawn under it.
    """
    SIZE_RANGE = (1, 3)
    """A grain's side, in whole pixels; at four a speck has a silhouette of its own."""
    SIZE_MIX = 1.0
    """The share of ``SIZE_RANGE`` one emission sweeps, across its grains.

    Swept rather than sampled, so coarse and fine grains appear together. Lower
    it to keep the coarsest size out.
    """
    TONE_MIX = (-0.4, 0.55)
    """The per-grain tone shift, off ``FXColors.dust_grain``.

    Both ways and wide: the bright grains carry the read against the tiles,
    the dark ones the texture.
    """
    GRAVITY = 620.0
    """Downward, and strong: a grain has nothing holding it up, and hanging specks read as insects."""
    DRAG = 2.5
    THROW = 34.0
    """Sideways fling, about twice the sheet's spread: a grain inside the sheet is invisible."""
    RISE = (30.0, 130.0)
    """Upward kick, as a range: a few grains go higher than the mass and land first."""
    BACK_SHARE = 0.35
    """The share of grains thrown back, against the direction of travel.

    A minority: the rest go sideways, where a boot throws the floor.
    """
    TTL = 0.22
    """How long a grain lives, well inside the sheet's: a grain that outlives the mass hangs in clear air."""
    FADE_IN = 0.02
    ALPHA_STEPS = 4
    MAX_ALPHA = 165
    """The most opaque a grain gets: two thirds of solid, the rest reads as air."""


class DashDust:
    """The dust a dash throws out of the fighter's trailing edge.

    A burst on the first tick, then small puffs on a cadence until the dash
    ends, so the mark is a ribbon along the path rather than one cloud where
    the fighter was. Thrown backwards, unscaled by any landing.

    Drawn without an ink rim, in two tones: at this size a grey outline makes
    a drawn shape of it. The lit edge along the top carries the separation.
    """

    SPAWN_EVERY = 0.02
    """Seconds between the puffs laid along the path, close to the afterimage cadence."""
    BURST_COUNT = 7
    """Puffs on the dash's first tick: the shove off the floor.

    Laid across the fighter's width, like the landing fan. The first number to
    give way to the family's budget, since the ribbon cannot be truncated.
    """
    TICK_COUNT = 4
    """Puffs on every later emission, filling in the ribbon.

    A dash spends at most a burst and three ribbons -- nineteen puffs at any
    frame rate -- inside the family's twenty.
    """
    BURST_TTL = 0.7
    TICK_TTL = 0.5
    """How long a puff lives.

    Longer than the dash, so the trail is still evaporating after the fighter
    left it. They also cap how high a puff may be kicked: it turns over at
    ``kick / GRAVITY`` seconds and must be coming down before it fades, or it
    reads as smoke (``test_the_trail_plume_turns_over_before_it_fades``).
    """
    BURST_RADIUS = 8.0
    TICK_RADIUS = 5.0
    """Puff radius, as shares of the painted sheet.

    The burst clears the body it is behind without becoming a screen in front
    of the fighter.
    """
    FADE_IN = 0.04
    """Short: the fighter crosses most of the ribbon in 0.14 s, so a slow ramp shows dust where he is not."""
    GRAVITY = 120.0
    """Downward, so a kicked puff rises and comes back down along the path."""
    KICK = (30.0, 80.0)
    """The upward speed each burst puff is kicked to.

    A range, so the burst stacks into a plume with lobes at several heights.
    The top is capped by ``GRAVITY * BURST_TTL`` (84): eighty turns over at
    0.67 s against a 0.7 s life.
    """
    TICK_KICK = 56.0
    """The upward speed of the ribbon's puffs, uniform.

    Enough to lift the ribbon off the tiles it lies on, under the tick's own
    cap of ``GRAVITY * TICK_TTL`` (60). Uniform, because a height spread along
    a line reads as a mess rather than as a ribbon.
    """
    THROW = 150.0
    """How hard the burst is shoved backwards; without it the cloud stays under the fighter."""
    TICK_THROW = 20.0
    """How hard the ribbon's puffs are shoved: thrown as hard as the burst, they clump back into it."""
    SPREAD = 40.0
    """Sideways fan of the burst and the ticks, the width the whole trail is laid in."""
    SPREAD_JITTER = 38.0
    """Random share of ``SPREAD`` per puff, kept under it so no puff lands outside the fan."""
    BACK_OFFSET = 0.4
    """Where along the body the trail is laid, as a fraction of its width: the trailing edge."""

    STEPS = 4
    BUCKETS = (4, 6, 9)
    """The radii a puff is painted at, smallest first; discrete, like the landing ladder."""
    GROWTH = 0.3
    """How much further the sheet reaches at each step, as a share of its radius.

    Steeper than the landing sheet's, so a trail left behind does not look cut
    off. Growth puts volume at the puff's peak, where it is read; past 0.3 it
    buys little height for a lot of width.
    """
    STEP_OPENS = 0.5
    """The share of the life the trail takes to open over."""
    MOTES = 11
    """How many parts the sheet is built from; at this size they are its only edge."""
    BASE_SHARE = (0.24, 0.32)
    """The lower band's parts, as shares of the radius: large enough to touch, one mass."""
    TOP_SHARE = (0.1, 0.15)
    """The fringe's parts, finer than the landing sheet's, so the burst reads as a mass first."""
    MOTE_SPREAD = 0.98
    """How far the band reaches either side of its centre, as a share of the radius."""
    MOTE_RISE = (0.1, 0.66)
    """How far above the band's floor the fringe sits: taller than the landing's, since it hangs in air."""
    MOTE_BASELINE = 0.3
    """Where the band's floor sits below centre, as a share of the radius."""
    MOTE_EVERY = 3
    """Every ``n``-th fringe part is drawn at the top of ``TOP_SHARE`` instead."""
    CHIP_SHARE = 0.78
    """The share of parts drawn as chips: the trail is read from further off, where arcs blur into beads."""
    CHIP_SIDES = (4, 6)
    """How many edges a chip has; no triangles, for the landing sheet's reason."""
    CHIP_TURN = 1.0
    """How far a chip's heading is drawn from, as a share of a full turn."""
    CHIP_GROW = 1.35
    """How much bigger a chip is drawn than the disc it replaces, by radius."""
    SQUASH = 0.66
    """How flat the first step is, as a share of the sheet's height."""
    TINT = (-0.12, 0.18)
    """The per-puff body shift: narrower and brighter than the landing's, read faster."""
    VARIANTS = 5
    """How many distinct silhouettes an emission draws from.

    One per burst slot; the ticks use the first ones, so neighbouring ticks match.
    """
    TTL_STAGGER = (0.75, 1.0)
    """Per-puff life, as a share of ``BURST_TTL`` or ``TICK_TTL``, longer for the outer puffs."""
    RADIUS_JITTER = 1.5
    """Per-puff radius, small: burst and ticks already differ by most of a factor of two."""


class FootstepTier(NamedTuple):
    """One locomotion tier's dust: how far between steps, and how scattered.

    Cadence and spread are what the eye reads as gait. Size cannot carry it --
    every small request is drawn at the same ladder bucket -- and a foot lands
    no higher at a run than at a walk.
    """

    step_distance: float
    """Pixels of ground covered between two steps.

    Paced by distance, so the marks are evenly spaced on the floor.
    """
    spread: float
    """This tier's share of ``FootstepDust.SPREAD``.

    Below one the pair is a single mark under the heel; above it the two
    halves of a step separate.
    """


class FootstepDust:
    """The dust a fighter's feet throw off while it walks, runs or turns.

    The mark that says a fighter is moving at all, between the landing ("how
    hard") and the dash ("a shove").

    The cadence is per tier, read by state name: :data:`TIER` has a row per
    ground state, :data:`SILENT` the states that leave nothing, and anything
    else (an enemy patrolling) gets :data:`DEFAULT_TIER`. The name rather than
    the speed, because ``resolve_locomotion_state`` already classifies with
    hysteresis; re-deriving it from the speed would make the dust flicker.
    ``test_fx_invariants`` checks every key against ``PlayerState``.

    ``MIN_STEP_EVERY`` caps the cadence so a run stays a footstep and does not
    become a second dash ribbon. The mark is laid behind the trailing foot,
    since the plane is painted under the fighter.
    """

    TIER: dict[str, FootstepTier] = {
        "walk": FootstepTier(40.0, 0.6),
        "run": FootstepTier(14.0, 1.15),
        "turn": FootstepTier(Turn.STEP_DISTANCE_PX, Turn.SPREAD),
    }
    """The ground tiers that mark the floor, keyed on ``PlayerState`` values.

    ``turn`` has a row because a pivot covers no distance, and the comb is
    paced by distance.
    """
    SILENT: frozenset[str] = frozenset({"walk_slow"})
    """The ground tiers that leave no dust at all.

    Named, so "silent" and "not a ground tier" stay two different answers.
    ``walk_slow`` is the guard's shuffle: marking it would say the fighter is
    travelling while he holds still.
    """
    DEFAULT_TIER = FootstepTier(14.0, 1.15)
    """What a fighter not in :data:`TIER` gets: the run row.

    Repeated rather than referenced; ``test_the_default_footstep_tier_is_the_run_row``
    keeps the two equal.
    """
    MIN_STEP_EVERY = 0.085
    """The shortest interval between two steps, in seconds.

    About twelve steps a second, close to the run animation's leg change; the
    run row alone would ask for twenty-five, which is a ribbon.
    """
    MIN_SPEED = 20.0
    """Below this ground speed, a fighter leaves nothing: no mark per frame of a friction settle."""
    COUNT = 2
    """Puffs in one step: two side by side read as a scuff, one as a speck."""
    RADIUS = 4.0
    """Per-puff radius, as a request to the trail's ladder.

    Drawn at the nearest of ``DashDust.BUCKETS``, so anything under six gives
    the same pixels: the smallest mark the plane can draw. Speed is said by
    the cadence, not the size.
    """
    TTL = 0.3
    """How long a step lives: the most frequent mark, so the shortest-lived, or the comb becomes a haze."""
    FADE_IN = 0.03
    """Fast: the fighter is already leaving the mark."""
    GRAINS = 3
    """Grit thrown with a step, from the ``dust_grain`` budget; without it a step is a smudge."""
    KICK = (14.0, 26.0)
    """The upward speed each puff is kicked to: a couple of pixels of arc, enough to say the ground moved."""
    THROW = 26.0
    """How hard a puff is thrown back against the direction of travel: the dust the heel pushed."""
    SPREAD = 12.0
    """The sideways spread of the pair at one share, in px/s; each tier scales it."""
    BACK_OFFSET = 0.35
    """Where along the fighter the mark is laid, as a share of his width: always the same place, so it reads as a comb."""
    FOOT_ALTERNATE = 0.18
    """How far either side of the trailing edge each foot lays its step, as a share of his width.

    The alternation reads as two feet; the parity comes free from the step count.
    """
    GRAVITY = 120.0
    """Downward, so the puff is back on the ground before it fades."""
    DRAG = 4.0
    """Horizontal drag, so a mark thrown back does not streak along the path."""
    RADIUS_JITTER = 1.0
    """Per-puff radius jitter, small, so the two halves of a step read as one scuff."""
    TINT = (-0.08, 0.12)
    """The per-puff body shift: narrow, since many steps are on screen at once."""
    TONES = 4
    """How many discrete tones the tint is drawn in, and so how many ladders.

    The ladder cache is keyed on the tone, so a continuous tone missed it on
    every step and grew it without bound. One bucket, four tones and two
    silhouettes cap the footstep at eight ladders
    (``test_a_footstep_cannot_grow_the_ladder_cache``).
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
    ARC_TTL = 0.26
    ARC_FLASH = 42.0
    #: How far the shield pushes out from the contact over its life, and how
    #: thick its band is.
    ARC_PUSH = 7.0
    ARC_BAND = 3
    #: The sparks thrown off the shield: how many, over what fan either side of
    #: the blow (degrees), how far they fly and how long each streak is.
    SPARKS = 6
    SPARK_FAN = 55.0
    SPARK_REACH = 10.0
    SPARK_LENGTH = 5.0
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

    ``_shatter_step`` depends only on its progress, its seed and the side, so
    each layout is painted once and reused: the most expensive effect in the
    plane is cached by this bound. Eight is enough that a repeat goes unseen
    in a 0.3 s break.
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


class Corpse:
    """The body of a fighter the last hit killed, thrown by that hit.

    The fighter leaves the simulation on the tick it dies; the body is a
    particle, so it collides with nothing and is never snapshotted.

    It leaves with the velocity the killing hit gave the fighter, times
    ``BOOST``, and never slower than ``MIN_KICK`` sideways and ``MIN_POP``
    upward, so a kill by a jab still reads as a kill. It falls under
    ``GRAVITY``, tumbles ``SPIN`` degrees a second in ``SPIN_STEP`` notches
    (whole notches: a continuous rotation of pixel art shimmers), rebounds
    off the height its feet were at with ``BOUNCE`` of its fall and
    ``GROUND_KEEP`` of its run, and is fully drawn until ``FADE_FROM`` of its
    life, then steps out.
    """

    TTL = 0.7
    GRAVITY = 1500.0
    DRAG = 0.6
    BOOST = 1.25
    MIN_KICK = 180.0
    MIN_POP = -260.0
    SPIN = 540.0
    SPIN_STEP = 30
    BOUNCE = 0.3
    GROUND_KEEP = 0.6
    FADE_FROM = 0.45
    ALPHA_STEPS = 4
