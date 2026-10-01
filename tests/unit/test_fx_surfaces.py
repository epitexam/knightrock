"""FX particles: which ones may rebuild their surface, and which may not.

`src/core/fx/particles.py` builds a particle's pixels once, at construction. A few of
them then pick a different surface per frame from a ladder they built
alongside, and these tests pin which, because the difference is invisible in
a screenshot and invisible in a frame time, and the mistake is easy to
reintroduce by "tidying" an update method.
"""

import os
from collections.abc import Iterator

import pygame
import pytest

from src.core.fx import (
    DashDustParticle,
    DizzyVortexParticle,
    DustParticle,
    FootstepDustParticle,
    GrainParticle,
    ShatterArcParticle,
    SweatParticle,
    clear_frame_cache,
    dash_frames,
    puff_frames,
    spawn_dash_dust,
    spawn_footstep_dust,
    spawn_landing_dust,
    spawners,
    vortex_frames,
)
from src.core.fx import particles as particles
from src.core.settings import DashDust, Dust, FootstepDust, FxDizzy, FxGuard


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((64, 64))


@pytest.fixture(autouse=True)
def _pinned_fx_rng() -> Iterator[None]:
    """Fix the draw, because these tests assert on the pixels it produces.

    Several spawners jitter from the FX module's own RNG, so which way a
    puff lands or how a fragment scatters is a function of how many draws
    the tests before them happened to make. Left alone that made a test here
    pass on its own and fail in the full suite -- a result that is evidence
    of the run's order rather than of the rule it claims to check.
    """
    spawners._fx_rng.seed(0xF00D)
    yield


def test_a_shatter_picks_its_failure_from_a_shared_ladder() -> None:
    """The break's geometry is painted per layout, not per break.

    This is the plane's largest single frame operation and it was built per
    spawn: 81 arc strokes across three steps, off a seed drawn from 65 536
    values on every break, measured at 1.14 ms against a 16.7 ms budget. Six
    times a second in a parry chain that is a hitch, not a cost.

    So the claim is the share, and it is a share by *value* like the dust
    ladders above: two breaks of the same side and the same layout hold one set
    of surfaces, and a seed outside the grid is folded into it rather than
    widening the table.
    """
    clear_frame_cache()
    one = ShatterArcParticle((0.0, 0.0), 1.0, seed=3)
    same = ShatterArcParticle((0.0, 0.0), 1.0, seed=3 + FxGuard.SHARD_SEEDS)
    other_side = ShatterArcParticle((0.0, 0.0), -1.0, seed=3)

    assert one.steps[0] is same.steps[0], "the same layout is one set of surfaces"
    assert one.steps[0] is not other_side.steps[0], "and a side is a different one"
    assert len(particles._shard_cache) == 2
    clear_frame_cache()


def test_the_shard_ladder_cannot_outgrow_its_grid() -> None:
    """The bound is the grid, not the number of breaks.

    An unbounded cache keyed on a per-spawn seed is a session-long leak of the
    plane's largest surfaces, which is the same trap the FX plane's own scale
    cache documents avoiding for the particle plane. So the ceiling is what the
    key space says it is -- two sides by ``SHARD_SEEDS`` -- and twenty breaks
    that each draw a fresh seed must not paint twenty layouts.
    """
    clear_frame_cache()
    spawners._fx_rng.seed(0x5A4D)
    for _ in range(20):
        for side in (1.0, -1.0):
            ShatterArcParticle((0.0, 0.0), side, seed=spawners._fx_rng.randrange(1 << 16))

    grid = 2 * FxGuard.SHARD_SEEDS
    assert len(particles._shard_cache) == grid, (
        f"forty breaks painted {len(particles._shard_cache)} ladders, over a grid of {grid}"
    )
    clear_frame_cache()


def test_a_shatter_sees_every_step_of_its_ladder() -> None:
    """It animates by stepping a table, and the table has the ladder's length.

    The same claim as the puff's, and it matters here for the same reason: a
    break is the one moment the plane spends real time, so it has to be steps
    off a built set rather than geometry rebuilt on the tick.
    """
    clear_frame_cache()
    particle = ShatterArcParticle((0.0, 0.0), 1.0, seed=1)
    seen = [particle.image]

    for _ in range(int(FxGuard.SHARD_TTL * 60)):
        particle.update(1 / 60)
        seen.append(particle.image)

    assert len(particle.steps) == FxGuard.SHARD_STEPS
    assert len(set(seen)) > 1, "the ring has to actually come apart"
    assert all(any(step is frame for frame in particle.steps) for step in seen), (
        "and every step it shows has to be one built once"
    )
    clear_frame_cache()


def test_the_first_step_of_a_break_is_the_whole_ring_for_every_layout() -> None:
    """At zero spread the seed cannot show, and that is why the table is small.

    Worth pinning because it reads as a bug otherwise: eight layouts of a
    break share a byte-identical first frame, and the eye is right to see one
    intact ring in all of them. It is also the reason ``SHARD_SEEDS`` buys two
    distinct frames per side rather than three -- the whole ring is one frame,
    shared, and only the spread is per layout.

    If a future change made the intact ring vary by layout it would not be
    wrong, but this test is what would say so.
    """
    layouts = range(FxGuard.SHARD_SEEDS)
    whole = {_pixels(ShatterArcParticle((0.0, 0.0), 1.0, seed=s).steps[0]) for s in layouts}
    spread = {_pixels(ShatterArcParticle((0.0, 0.0), 1.0, seed=s).steps[-1]) for s in layouts}

    assert len(whole) == 1, "the whole ring does not depend on the layout"
    assert len(spread) == len(layouts), "but the spread does"
    clear_frame_cache()


def _pixels(surface: pygame.Surface) -> bytes:
    """A surface's bytes, for comparing two of them for equality.

    ``Surface.tobytes`` does not exist and ``pygame.image.tostring`` is
    deprecated, and ``get_view`` is what the test suite already reaches for
    wherever it needs to know what a surface actually holds.
    """
    return bytes(surface.get_view())


def test_a_sweat_drop_surface_is_built_once_and_only_faded() -> None:
    """A drop's shape is fixed, so rebuilding it would redraw the same pixels.

    This property has moved house three times now: it was pinned on the dash
    comet, then on the speed line, then on the dust, all of which are gone or
    have become ladders. It stays on sweat because the claim is about the
    module and not about one particle -- every mark here either builds its
    surface at construction and then only moves and fades, or steps through a
    ladder it built alongside, and a "tidying" of an update method is the
    mistake it catches.
    """
    particle = SweatParticle((0.0, 0.0), (60.0, -20.0))
    original = particle.image

    for _ in range(8):
        particle.update(1 / 60)

    assert particle.image is original, "the drop must not rebuild its surface"
    assert particle.image.get_alpha() < 255, "and it must still fade"


def test_a_puff_picks_its_billow_from_a_shared_ladder() -> None:
    """The puff opens, and every step it opens to is one the session built once.

    The dust is the particle that was rebuilt per particle per frame: it used
    to scale its own copies of three PNGs at construction and then swap
    between them, and a landing put six of those on screen at once. It steps a
    shared ladder now, for the same reason the swirl does.
    """
    clear_frame_cache()
    ladder = puff_frames(Dust.PUFF_RADIUS)
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))
    seen = [particle.image]

    for _ in range(4):
        particle.update(1 / 60)
        seen.append(particle.image)

    assert len(ladder) == Dust.PUFF_STEPS
    assert len(set(seen)) > 1, "the puff has to billow"
    assert all(any(step is frame for frame in ladder) for step in seen), (
        "and every step it shows has to be one built once"
    )
    assert particle.ladder is ladder, "and the ladder is shared, not per puff"
    clear_frame_cache()


def test_a_hard_landing_does_not_paint_a_new_puff_surface() -> None:
    """A landing is twelve puffs and it must not be twelve sets of surfaces.

    The reason the ladder is keyed on a discrete radius and a discrete tone
    rather than on whatever the spawner asked for: this is the allocation
    ``notes/refacto.md`` flags as the FX plane's main remaining cost, and a
    landing is exactly when a dozen of them happen on the same tick.

    The bound is the grid, not the fan. The radius carries a jitter, so any
    one landing lands on several buckets and a later one may reach a bucket
    the first missed -- but the cache can never outgrow the grid, however
    many landings go through it. That ceiling is the whole reason for
    snapping: an unbounded cache keyed on a continuous radius is the same
    allocation as no cache at all.
    """
    clear_frame_cache()
    lander = _lander()
    for _ in range(12):
        spawn_landing_dust(pygame.sprite.Group(), lander, Dust.MIN_FALL_SPEED * 2.0)

    grid = len(Dust.PUFF_BUCKETS) * len(Dust.SIZE_PROFILE) * Dust.PUFF_VARIANTS
    assert 0 < len(particles._puff_cache) <= grid, (
        f"twelve landings painted {len(particles._puff_cache)} ladders, over a grid of {grid}"
    )
    clear_frame_cache()


def test_two_puffs_of_one_size_and_tone_share_their_ladder() -> None:
    """The share is by value, so two puffs of a size hold one set of surfaces."""
    clear_frame_cache()
    one = DustParticle((0.0, 0.0), (0.0, 0.0), radius=5.0, tint=0.0)
    two = DustParticle((0.0, 0.0), (0.0, 0.0), radius=5.4, tint=0.0)

    assert one.ladder is two.ladder, "5.0 and 5.4 are the same bucket"
    assert len(particles._puff_cache) == 1
    clear_frame_cache()


def _lander() -> object:
    """A stand-in with the one attribute the landing fan reads."""
    from types import SimpleNamespace

    return SimpleNamespace(hitbox=pygame.FRect(100.0, 100.0, 40, 48))


def _dasher() -> object:
    """A stand-in with the three attributes the dash trail reads."""
    from types import SimpleNamespace

    return SimpleNamespace(
        hitbox=pygame.FRect(100.0, 100.0, 40, 48),
        velocity=pygame.math.Vector2(1100.0, 0.0),
        facing_right=True,
    )


def test_a_trail_puff_picks_its_billow_from_a_shared_ladder() -> None:
    """The trail animates the way the landing puff does: by stepping a table.

    Same claim, and it matters more here. A dash lays puffs on a cadence for
    as long as the fighter is moving, so more of them are alive at once than a
    landing ever puts out, and the ladder is what keeps a burst and a ribbon
    from being a set of surfaces allocated on the tick.
    """
    clear_frame_cache()
    ladder = dash_frames(DashDust.BURST_RADIUS)
    particle = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.BURST_RADIUS)

    seen: list[pygame.Surface] = []
    for _ in range(int(DashDust.TICK_TTL * 60)):
        particle.update(1 / 60)
        seen.append(particle.image)

    assert len(ladder) == DashDust.STEPS
    assert len(set(seen)) > 1, "the trail has to billow"
    assert particle.ladder is ladder, "and the ladder is shared, not per puff"
    clear_frame_cache()


def test_a_dash_trail_does_not_paint_a_new_surface_per_puff() -> None:
    """A ribbon of puffs must stay a bounded number of ladders, however many dashes.

    The radius carries a jitter and the tone is spread across the emission's
    own length, so any one dash lands on several buckets and a later one may
    reach a bucket the first missed. What must not happen is a new ladder per
    particle: the cache can never outgrow the grid of discrete radii and tones
    however many dashes go through it.
    """
    clear_frame_cache()
    dasher = _dasher()
    for _ in range(20):
        spawn_dash_dust(pygame.sprite.Group(), dasher, burst=True)
        spawn_dash_dust(pygame.sprite.Group(), dasher)

    grid = len(DashDust.BUCKETS) * (DashDust.BURST_COUNT + 1) * DashDust.VARIANTS
    assert 0 < len(particles._dash_cache) <= grid, (
        f"twenty dashes painted {len(particles._dash_cache)} ladders, over a grid of {grid}"
    )
    clear_frame_cache()


def test_a_footstep_cannot_grow_the_ladder_cache() -> None:
    """The busiest mark in the plane, and the one with the most to lose from a miss.

    This is the same claim as the test above, for a mark that fires twelve times a
    second rather than five times per dash -- so its misses are not five rows on
    one frame, they are five rows every eighth of a second for as long as the
    player holds a direction.

    It was written with a continuous tone per puff, sampled from the FX stream,
    and the ladder is keyed on ``round(tint, 3)``: sixty seconds of running built
    383 ladders and the emitter's p95 sat at 828us, a fifth of a frame, on tick
    after tick, forever. The grid below is what bounds it instead: one radius
    bucket, four discrete tones, two silhouettes.

    Run long on purpose. A bound that only holds for a second of play is not a
    bound, and this is the one defect here that a short test would pass.
    """
    clear_frame_cache()
    walker = _dasher()
    walker.velocity = pygame.math.Vector2(350.0, 0.0)
    for step in range(1200):
        spawn_footstep_dust(
            pygame.sprite.Group(), walker, foot=bool(step % 2), tier=FootstepDust.TIER["run"]
        )

    grid = FootstepDust.TONES * min(FootstepDust.COUNT, DashDust.VARIANTS)
    assert 0 < len(particles._dash_cache) <= grid, (
        f"twenty seconds of walking painted {len(particles._dash_cache)} ladders, "
        f"over a grid of {grid}"
    )
    clear_frame_cache()


def test_a_footstep_draws_two_tones_and_never_one() -> None:
    """The reason the palette is indexed by the foot and not just by the slot.

    A two-puff step given one tone per slot reaches only the ends of the range,
    and a footstep given a random one reaches a new ladder every time. Indexing
    by the foot as well is what keeps a long comb from being a row of identical
    marks at zero cost, because the emitter is already carrying which foot it is.

    Held as a count because that is the whole of the guarantee: four tones over
    two feet, and both pairs inside the range rather than off its ends.
    """
    rows = {
        particles.footstep_tint(index, foot)
        for foot in (False, True)
        for index in range(FootstepDust.COUNT)
    }

    assert len(rows) == FootstepDust.TONES, f"all {FootstepDust.TONES} tones are reachable: {rows}"
    low, high = FootstepDust.TINT
    # A tolerance, because the row is built by interpolation and the top of it
    # lands at 0.12000000000000004 rather than at 0.12. Harmless -- the ladder
    # key rounds the tone to three places -- but it is the kind of thing an
    # exact comparison turns into a red test every few years.
    assert all(low - 1e-9 <= tone <= high + 1e-9 for tone in rows), (
        f"and all inside {FootstepDust.TINT}: {rows}"
    )
    assert len({particles.footstep_tint(0, False), particles.footstep_tint(1, False)}) == 2, (
        "and one step's own halves never match on tone"
    )


def test_two_trail_puffs_of_one_size_and_tone_share_their_ladder() -> None:
    """The share is by value, so the burst and the ticks that match it hold one set."""
    clear_frame_cache()
    burst = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.BURST_RADIUS, tint=0.0)
    tick = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.TICK_RADIUS, tint=0.0)

    assert burst.ladder is not tick.ladder, "two sizes, two ladders"
    assert len(particles._dash_cache) == 2
    clear_frame_cache()


def test_the_trail_tones_are_spread_across_the_emission_and_not_a_fixed_row() -> None:
    """A two-puff tick and a five-puff burst both have to get a spread of tones.

    Keyed on a fixed palette, the two lengths would draw the tick as two
    adjacent tones -- two near-identical clouds -- and leave the top of the
    range unused on the burst, which is the one mark the dash is read from.
    """
    from src.core.fx import dash_tint

    tick = [dash_tint(index, DashDust.TICK_COUNT) for index in range(DashDust.TICK_COUNT)]
    burst = [dash_tint(index, DashDust.BURST_COUNT) for index in range(DashDust.BURST_COUNT)]

    assert tick[0] == DashDust.TINT[0]
    assert tick[-1] == DashDust.TINT[1], "a tick reaches both ends of the range"
    assert burst[-1] == DashDust.TINT[1], "and so does the burst"
    assert len(set(tick)) == len(tick) and len(set(burst)) == len(burst)


def test_a_display_format_change_forgets_the_trail_ladders() -> None:
    """The ladders are memoized surfaces, so a stale one is a stale image.

    ``pygame.display.set_mode`` invalidates every converted surface, so the
    trail cache has to go with it or the plane keeps handing back pixels that
    no longer exist in the new format.
    """
    clear_frame_cache()
    DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.BURST_RADIUS)
    assert particles._dash_cache

    clear_frame_cache()

    assert particles._dash_cache == {}


def test_a_footstep_steps_the_trails_ladder_and_paints_nothing() -> None:
    """The most frequent mark in the plane cannot be the one that allocates.

    Twelve steps a second times two puffs is the largest number of dust
    particles the game ever spawns in a second, and the footstep was added as a
    subclass precisely so it would share the trail's cache rather than build a
    second grid. So the claim is stronger than "it does not repaint": the cache
    it reaches into is the one the trail already filled, and a session of
    footsteps adds no row to it at all.
    """
    clear_frame_cache()
    step = FootstepDustParticle((0.0, 0.0), (0.0, 0.0), tint=0.05, variant=1)
    trail = DashDustParticle((0.0, 0.0), (0.0, 0.0), tint=0.05, variant=1)
    ladders_after_two = len(particles._dash_cache)

    for _ in range(60):
        step.update(1 / 60)

    assert step.ladder is trail.ladder, "the footstep holds a reference, not a copy"
    assert len(particles._dash_cache) == ladders_after_two, (
        "and sixty ticks of walking added no frame to the table"
    )
    assert len({id(frame) for frame in step.ladder}) == len(step.ladder), (
        "each step of the ladder is a distinct surface, reused across particles"
    )
    clear_frame_cache()


def test_every_particle_paints_its_first_surface_exactly_once() -> None:
    """The one paint, for every family -- counted, not read.

    Every particle builds its pixels in ``FxParticle.__init__``, and three of
    them were painting a second time immediately afterwards. The grain did it by
    assigning ``self.image`` before handing the same arguments straight back, so
    the base painted again: two surfaces of one to three pixels, allocated and
    dropped, for every grain in the plane -- and the grains are its most numerous
    particle, fourteen on a landing and three on every footstep.

    The sheets did it the other way round, reaching past the base for
    ``ladder[0]`` and rebuilding a rect off it, which is the same surface the base
    had already put on the sprite. That is cheaper than the grain's, but it lands
    on the busiest emitters in the plane and it is the same mistake.

    Counted rather than checked by identity, because both bugs produce an image
    byte-identical to the one the base built: there is nothing to assert about
    the result that distinguishes them. Only the number of paints does.

    The painters are patched at the module they are *called* from rather than at
    their definition, because ``DashDustParticle._paint`` and ``FootstepDustParticle
    ._paint`` are the same function on the same base -- patching the definition
    would count one row for either and hide the other.
    """
    counted: dict[str, int] = {}

    def count(name: str, fn: object) -> object:
        def once(*args: object, **kwargs: object) -> object:
            counted[name] = counted.get(name, 0) + 1
            return fn(*args, **kwargs)  # type: ignore[operator]

        return once

    painted = {
        "_grain_surface": particles._grain_surface,
        "_puff_step": particles._puff_step,
        "_dash_step": particles._dash_step,
    }
    sweat_paint = SweatParticle._paint
    try:
        particles._grain_surface = count("grain", painted["_grain_surface"])  # type: ignore[assignment]
        particles._puff_step = count("landing", painted["_puff_step"])  # type: ignore[assignment]
        particles._dash_step = count("trail", painted["_dash_step"])  # type: ignore[assignment]
        SweatParticle._paint = count("sweat", sweat_paint)  # type: ignore[method-assign]

        clear_frame_cache()
        GrainParticle((0.0, 0.0), (0.0, 0.0), size=2, tint=0.1)
        assert counted.get("grain") == 1, f"a grain paints once, not twice: {counted}"
        clear_frame_cache()

        counted.clear()
        DustParticle((0.0, 0.0), (0.0, 0.0))
        assert counted.get("landing") == Dust.PUFF_STEPS, (
            f"the landing sheet paints one row of {Dust.PUFF_STEPS}: {counted}"
        )
        clear_frame_cache()

        counted.clear()
        FootstepDustParticle((0.0, 0.0), (0.0, 0.0))
        assert counted.get("trail") == DashDust.STEPS, (
            f"and the footstep one row of {DashDust.STEPS}: {counted}"
        )
        clear_frame_cache()

        counted.clear()
        SweatParticle((0.0, 0.0), (0.0, 0.0))
        assert counted.get("sweat") == 1, f"and a sweat drop paints once: {counted}"
        clear_frame_cache()
    finally:
        particles._grain_surface = painted["_grain_surface"]  # type: ignore[assignment]
        particles._puff_step = painted["_puff_step"]  # type: ignore[assignment]
        particles._dash_step = painted["_dash_step"]  # type: ignore[assignment]
        SweatParticle._paint = sweat_paint  # type: ignore[method-assign]


def test_the_ladders_hold_no_memo_of_their_own() -> None:
    """Every cache in this module is a dict keyed by its value; none is a bare global.

    The footstep's tone row was memoized once, behind a ``global``, and it was the
    only mutable piece of module state in the file. Worth a test because the two
    obvious reasons to add another both look like that one: the row is read on
    every spawn, and it never changes. Neither matters here -- four pieces of
    arithmetic twenty times a second measured at nineteen microseconds per
    second -- and the cost of the memo is not the memory. It is a value that can
    outlive the setting it was built from and then quietly ignore a changed
    ``FootstepDust.TINT``.

    So the rule is the shape rather than the absence: a module-level assignment
    holding something mutable and unkeyed is a memo, and a memo is what this
    refuses. Immutable module-level constants are exempt, and so are the caches,
    because a dict is keyed by the value that selects it and
    ``clear_frame_cache`` is what empties it.

    Scoped to the upper-case names, and that is this module's convention rather
    than a coincidence: every cache, sentinelled memo and seed here is named that
    way, so a lowercase memo would be the first thing not to follow the
    convention in the file. What it inspects is four names today -- two cache
    dicts, a seed and ``ALPHA_STEPS`` -- and a fifth arriving as a list is what
    makes it red.
    """
    mutable = {
        name: type(value).__name__
        for name, value in vars(particles).items()
        if name.isupper()
        and not name.startswith("__")
        and not isinstance(value, (bool, bytes, float, int, str, tuple, frozenset, type))
        and not isinstance(value, dict)
    }

    assert not mutable, f"the ladders keep no mutable state of their own: {mutable}"


def test_the_puff_fade_matches_its_ttl_curve() -> None:
    """Freezing the surface must not freeze the fade with it."""
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))
    particle.max_ttl = Dust.TTL

    particle.update(Dust.TTL * 0.5)
    halfway = particle.image.get_alpha()
    particle.update(Dust.TTL * 0.25)
    later = particle.image.get_alpha()

    assert 0 < later < halfway < 255


def test_a_puff_still_follows_its_position() -> None:
    """The rect is per-frame even though the surface is not.

    A puff travels, so the claim is not that the position holds still but
    that the drawn rect is re-cut around wherever the particle now is.
    """
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))
    particle.pos.update(120.0, 40.0)

    particle.update(1 / 60)

    assert (particle.rect.centerx, particle.rect.centery) == pytest.approx(tuple(particle.pos))


def test_a_puff_still_reaps_at_the_end_of_its_life() -> None:
    particle = DustParticle((0.0, 0.0), (60.0, -20.0))

    particle.update(Dust.TTL + 1.0)

    assert particle.alive() is False


def test_a_swirl_picks_its_rotation_step_from_a_shared_ladder() -> None:
    """The vortex animates by stepping a ladder, not by redrawing its arms.

    It used to draw three arms of three polygons per particle per frame, and
    a stun puts up to four of them on screen at once.
    """
    clear_frame_cache()
    particle = DizzyVortexParticle((0.0, 0.0))
    frames = vortex_frames()
    seen = [particle.image]

    for _ in range(4):
        particle.update(0.1)
        seen.append(particle.image)

    assert len(frames) == FxDizzy.VORTEX_FRAMES
    assert len(set(seen)) > 1, "the swirl has to animate"
    assert all(any(step is frame for frame in frames) for step in seen), (
        "and every step it shows has to be one it built once"
    )
    clear_frame_cache()
