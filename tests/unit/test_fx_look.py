"""FX behaviour the visual pass changed: layering, contact points and budgets.

These are the properties a screenshot cannot show and a frame time cannot
reveal: which plane a mark is painted in, where a burst is thrown from, and
that a big burst cannot starve the effects that have to keep animating.
"""

import math
import os
from collections.abc import Iterator
from types import SimpleNamespace

import pygame
import pytest
from pygame.sprite import Group

from src.core import fx
from src.core.colors import Color, Colors, FXColors
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.viewport import Viewport
from src.core.fx import (
    FX_FAMILY_BUDGETS,
    MAX_FX_SPRITES,
    DashDustParticle,
    DustParticle,
    FootstepDustParticle,
    GrainParticle,
    OrbitParticle,
    ShatterArcParticle,
    ShieldArcParticle,
    particles,
    spawn_dash_dust,
    spawn_dizzy_vortex,
    spawn_footstep_dust,
    spawn_footstep_grains,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_landing_grains,
    spawners,
)
from src.core.fx.draw import snap
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.settings import (
    DashDust,
    Dust,
    DustGrain,
    FootstepDust,
    FxGuard,
)
from src.core.sprite_groups import SpriteGroups
from src.states.player_states import PlayerState


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


@pytest.fixture(autouse=True)
def _pinned_fx_rng() -> Iterator[None]:
    """Fix the draw, because these tests assert on the pixels it produces.

    `spawn_shatter_arc` seeds its fragments from the module's own RNG, so
    which way the pieces scatter is a function of how many draws the tests
    before it happened to make. Left alone that made a test here pass on its
    own and fail in the full suite -- a result that is evidence of the run's
    order rather than of the rule it claims to check.
    """
    spawners._fx_rng.seed(0xF00D)
    yield


def _entity(x: float = 100.0, y: float = 100.0, facing: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        hitbox=pygame.FRect(x, y, 40, 48),
        velocity=pygame.math.Vector2(600.0, 0.0),
        facing_right=facing,
    )


def test_dust_is_painted_under_the_moving_plane() -> None:
    """A fighter must not be painted over by the dust they kicked up."""
    puff = DustParticle((0.0, 0.0), (0.0, 0.0))

    assert puff.behind is True
    assert FootstepDustParticle((0.0, 0.0), (0.0, 0.0)).behind is True
    assert ShieldArcParticle((0.0, 0.0), 1.0).behind is False


def _make_renderer() -> tuple[Renderer, SpriteGroups]:
    """A renderer on a target built the way the game builds one.

    The framing is the game's: a test that picks a framing and a surface
    separately can produce a pair the game would refuse, and then it tests a
    configuration that cannot occur.
    """
    surface = Viewport(
        DEFAULT_FRAMING,
        (round(DEFAULT_FRAMING.width), round(DEFAULT_FRAMING.height)),
    ).surface
    camera = Camera.for_target(surface)
    camera.set_world_size(DEFAULT_FRAMING.width, DEFAULT_FRAMING.height)
    return Renderer(surface, camera), SpriteGroups()


def test_ground_marks_are_queued_before_the_entities_and_sparks_after() -> None:
    renderer, groups = _make_renderer()
    decal = spawn_impact_decal(groups.fx_sprites, _entity(200.0, 300.0))
    walker = pygame.sprite.Sprite()
    walker.image = pygame.Surface((8, 8), pygame.SRCALPHA)
    walker.rect = pygame.Rect(200, 300, 8, 8)
    groups.all_sprites.add(walker)
    spark = fx.spawn_dizzy_stars(groups.fx_sprites, _entity(300.0, 300.0))[0]
    groups.fx_sprites.add(spark)

    blits = renderer._collect_visible_blits(groups)

    assert decal is not None
    images = [surface for surface, _ in blits]
    assert images.index(decal.image) < images.index(walker.image), "the mark goes under the entity"
    assert images.index(spark.image) > images.index(walker.image), "and the spark over it"


def test_a_hard_landing_scales_with_the_fall_speed() -> None:
    """The count is fixed and the size is not, so a fall reads as a fall."""
    soft = spawn_landing_dust(Group(), _entity(200.0, 300.0), Dust.MIN_FALL_SPEED)
    hard = spawn_landing_dust(Group(), _entity(200.0, 300.0), Dust.MIN_FALL_SPEED * 3.0)

    assert len(soft) == len(hard)
    assert hard[0].radius > soft[0].radius
    assert abs(hard[0].velocity.x) + abs(hard[0].velocity.y) > abs(soft[0].velocity.x) + abs(
        soft[0].velocity.y
    )


def test_the_landing_mark_is_wider_for_a_harder_fall() -> None:
    soft = spawn_impact_decal(Group(), _entity(200.0, 300.0), Dust.MIN_FALL_SPEED)
    hard = spawn_impact_decal(Group(), _entity(200.0, 300.0), Dust.MIN_FALL_SPEED * 3.0)

    assert soft is not None and hard is not None
    assert hard.image.get_width() > soft.image.get_width()
    assert hard.behind is True


def test_the_landing_mark_is_flat_on_the_ground_and_opens() -> None:
    """A mark on a floor is squashed and it widens; a disc floating above it is not.

    It used to be three thick tongues at 0, 120 and 240 degrees, which came
    out asymmetric about a vertical that means nothing on a floor, and five
    pixels thick against a fighter forty wide. A flat ring reads as the ground
    being struck, and opening says how hard.

    Measured on the lit pixels rather than on the surface: the surface is
    square, because it has to hold the widest step of the ladder, and a
    square surface says nothing about whether the mark inside it is flat.
    """
    decal = spawn_impact_decal(Group(), _entity(200.0, 300.0), Dust.MIN_FALL_SPEED * 2.0)
    assert decal is not None
    width, height = _ink_extent(decal.image)

    assert width > height * 2, f"a flat mark, not a disc: {width}x{height}"
    assert not decal.image.get_at((decal.image.get_width() // 2, decal.image.get_height() // 2))[
        3
    ], "and hollow: a mark is the rim the dust pushed out, not a filled blob"
    assert decal.steps[-1].get_width() > decal.steps[0].get_width(), "and it opens"


def _ink_extent(surface: pygame.Surface) -> tuple[int, int]:
    """The width and height of the lit pixels, not of the surface."""
    lit = [
        (x, y)
        for y in range(surface.get_height())
        for x in range(surface.get_width())
        if surface.get_at((x, y))[3]
    ]
    xs = [x for x, _ in lit]
    ys = [y for _, y in lit]
    return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def test_a_puff_is_a_sheet_of_grit_and_not_a_ball() -> None:
    """One disc reads as a ball, and four large ones read as a bubble.

    The lobes are what make it a cloud, and what the ink rim follows, so this
    is a claim about the outline: a silhouette as wide as it is tall, with
    nothing pushing out to one side, is the shape the puff had before the
    lobes existed -- and the shape it had again when four discs of comparable
    radius were unioned together, because that union is a smooth convex oval
    whatever the discs are offset by.

    The notches are the second half of the claim and the reason the lobes are
    small. A band of lobes at similar heights merges into one long level line,
    and a level line is a drawn shape; what makes grit read as grit is that the
    top edge is broken. So the last row of lit pixels has to contain gaps, and
    on the fully open step rather than the flat first one, which is the shape
    the player watches drift up.
    """
    puff = DustParticle((0.0, 0.0), (0.0, 0.0), radius=Dust.PUFF_RADIUS)

    flat = _ink_extent(puff.ladder[0])
    open_ = _ink_extent(puff.ladder[-1])
    assert flat[0] > flat[1], f"a puff leaves the ground flat: {flat}"
    assert open_[0] > open_[1] * 1.5, f"and is a band, not a disc, as it opens: {open_}"
    assert puff.ladder[-1].get_width() > puff.ladder[0].get_width(), "the billow widens"

    top = _top_breaks(puff.ladder[-1], FXColors.dust_lit)
    assert top > 0, f"the top edge of a sheet of grit is broken, not domed: {top} rise(s)"


def _top_breaks(surface: pygame.Surface, tone: Color) -> int:
    """How many times the mark's top edge steps back *up* as it crosses.

    The notch count, in the only form that means anything at this scale. A disc
    -- or a union of large discs, or a band of lobes all at the same height --
    has a top edge that only ever descends as it crosses, or stays level. What
    makes grit read as grit is that the edge comes back up, so the claim is
    about rises and not about the shape of any one run.

    Counted over the lit tone rather than over "any pixel", because the lit
    rim is the top of the silhouette by construction and the outline beneath it
    is where the lobes actually are.
    """
    lit = tuple(tone)
    profile = [
        min(
            (y for y in range(surface.get_height()) if surface.get_at((x, y))[:3] == lit),
            default=-1,
        )
        for x in range(surface.get_width())
    ]
    return sum(
        1 for before, after in zip(profile, profile[1:], strict=False) if 0 <= after < before
    )


def test_the_puff_light_is_a_rim_and_never_a_disc_of_highlight() -> None:
    """The one detail that made the dust read as a drawing for children.

    A puff used to carry a disc of ``dust_lit`` set into its own top-left
    corner, and a round patch of light inside a round mass is the oldest
    convention there is: it is how a bubble, a pearl, a marble and a
    children's-book cloud are all drawn. Nothing about the outline being lumpy
    survives it -- you can build a perfect dust silhouette and hang a sphere of
    highlight on it and the frame still says cartoon.

    The light is now a one-pixel rim along the top left of the whole sheet,
    which cannot contain a two-pixel square. That is not a tolerance, it is
    arithmetic: the rim is the shape drawn one pixel up and to the left and
    then overdrawn by itself, so a lit pixel at (x, y) needs the shape at
    (x+1, y+1) and not at (x, y), and a 2x2 block would need the shape at
    (x+1, y+1) and absent from it at the same time. Asserting it is asserting
    the construction, so the disc cannot come back as a matter of taste.
    """
    for radius in Dust.PUFF_BUCKETS:
        for variant in range(Dust.PUFF_VARIANTS):
            surface = DustParticle((0.0, 0.0), (0.0, 0.0), radius=radius, variant=variant)
            _no_solid_block(surface.ladder[-1], FXColors.dust_lit)
            assert _share(surface.ladder[-1], FXColors.dust_lit) < 0.35, (
                "and the light is a minority of the mark, not a second mass"
            )


def _no_solid_block(surface: pygame.Surface, tone: Color) -> None:
    """Fail if ``tone`` ever fills a two-by-two square of ``surface``."""
    lit = tuple(tone)
    for y in range(surface.get_height() - 1):
        for x in range(surface.get_width() - 1):
            block = [surface.get_at((x + dx, y + dy))[:3] == lit for dx in (0, 1) for dy in (0, 1)]
            assert not all(block), (
                f"a two-by-two block of {tone} at ({x}, {y}): that is a disc of "
                f"highlight, which is the cartoon tell"
            )


def _share(surface: pygame.Surface, tone: Color) -> float:
    """What share of the mark's lit pixels are ``tone``, from 0 to 1."""
    lit = tuple(tone)
    drawn = [
        (x, y)
        for y in range(surface.get_height())
        for x in range(surface.get_width())
        if surface.get_at((x, y))[3]
    ]
    if not drawn:
        return 0.0
    return sum(1 for x, y in drawn if surface.get_at((x, y))[:3] == lit) / len(drawn)


def test_the_sheet_is_faceted_and_a_disc_built_one_would_not_be() -> None:
    """The claim, measured on the layout rather than on the primitive.

    A silhouette made of arcs is a cluster of beads however many there are and
    however small: fifteen little circles make fifteen little bubbles along the
    outline, and what the eye reads is the arcs rather than the count. A sheet
    with a quarter of its outline in straight runs reads as *stuff* -- a flake
    off a floor, a grain -- which is the whole difference between gravel and
    foam.

    Two things have to hold, and neither is a pixel measurement. There have to
    be chips in the layout at all, and they have to be *big enough to show a
    side* at the sizes the fan is actually painted at: a chip three pixels
    across has an edge, and a chip one pixel across is a speck, which is the
    grain family's job and a sparkle at that.

    The size is checked as arithmetic on the layout rather than on the pixels,
    and deliberately so -- pygame fills the top of a radius-twelve disc with a
    six-pixel flat edge, so a circle is not obviously curved once it is on the
    grid, and a pixel test here would be measuring the rasteriser.
    """
    for variant in range(Dust.PUFF_VARIANTS):
        discs, chips = particles._puff_motes(variant)
        assert discs and chips, (
            f"variant {variant} is one kind of part only: {len(discs)} discs, {len(chips)} chips"
        )
        for radius in Dust.PUFF_BUCKETS:
            reach = radius * (1.0 + Dust.PUFF_GROWTH * (Dust.PUFF_STEPS - 1))
            widest = max((size * reach for _, _, size, _, _ in chips), default=0.0)
            assert widest * 2 >= 3.0, (
                f"a chip at the {radius} bucket is {widest * 2:.1f}px across: "
                f"below three it is a speck rather than a facet"
            )


def test_a_sheet_is_built_from_both_kinds_of_part() -> None:
    """A clean sweep of chips is a heap of debris, and a clean sweep of discs is
    a heap of beads. Neither is dust.

    The discs are there for the rounded shoulders that keep the silhouette from
    reading as a shard of glass, so the sheet has to keep some of them. Held on
    the settings rather than on the pixels, because what the pixels depend on is
    a seeded draw and what the settings promise is that the mix is a decision.
    """
    assert 0.0 < Dust.PUFF_CHIP_SHARE < 1.0
    assert 0.0 < DashDust.CHIP_SHARE < 1.0
    least = min(Dust.PUFF_CHIP_SIDES[0], DashDust.CHIP_SIDES[0])
    assert least >= 4, "a triangle at three pixels is a sparkle, not a facet"


def test_the_sheet_sits_on_a_shadow_rather_than_floating() -> None:
    """The mass has to be standing on something.

    A rim light alone describes a flat shape with one bright edge and no
    weight, which is what a decal looks like. The shadow pass puts a shade a
    pixel under the sheet, filling the gaps between the lobes along the bottom
    into a continuous dark base -- and it has to be its own tone. Sharing the
    rim's tone made a solid three-pixel band across the bottom of the mark, and
    a solid band across the base of a shape is a stripe.
    """
    surface = DustParticle((0.0, 0.0), (0.0, 0.0), radius=Dust.PUFF_RADIUS).ladder[-1]
    tones = _tones(surface)

    assert tuple(FXColors.dust_shade) in tones, "the sheet sits in its own shade"
    assert tuple(FXColors.dust_shade) != tuple(FXColors.dust_deep), (
        "and the shade is not the rim: one tone for both is a stripe across the base"
    )
    gap = sum(body - shade for body, shade in zip(FXColors.dust, FXColors.dust_shade, strict=True))
    assert gap > 60, f"and it reads as a step below the body, not a stain: {gap}"


def test_the_puff_rim_actually_separates_it_from_the_background() -> None:
    """The rim is the DA's reason for inking, so it has to be a real contrast.

    The old one sat 44 units under the body colour. At a one-pixel outline
    that is barely a shade, and against a bright background the cloud lost its
    edge and came out as a smudge -- which is the one thing the ink rule
    exists to prevent.
    """
    puff = DustParticle((0.0, 0.0), (0.0, 0.0), radius=Dust.PUFF_RADIUS)
    surface = puff.ladder[-1]

    tones = _tones(surface)
    rim = tuple(FXColors.dust_deep)
    body = tuple(FXColors.dust)

    assert rim in tones, "the rim is on the puff"
    assert body in tones, "and so is the body it separates"
    gap = sum(b - r for r, b in zip(rim, body, strict=True))
    assert gap > 80, f"a rim has to read against the body, not tint it: {gap}"


def _tones(surface: pygame.Surface) -> set[tuple[int, int, int]]:
    return {
        tuple(surface.get_at((x, y))[:3])
        for y in range(surface.get_height())
        for x in range(surface.get_width())
        if surface.get_at((x, y))[3]
    }


def test_a_fan_never_draws_the_same_sheet_twice() -> None:
    """A fan of one shape at four sizes is a spinner, not a landing.

    Tone and size are both global properties of a mark, and varying only those
    leaves the silhouette the same in every member -- which the eye reads as a
    stamp rather than as an event. So the variants are indexed off the tone's
    own palette rather than alongside it: with the same index for both, a fan
    of four walked the diagonals of a four-by-four grid and landed on
    (0,0) (1,1) (2,2) (3,3), so every member matched another on tone *and* on
    shape at the same time.
    """
    pairs = [(puff.tint, puff.variant) for puff in spawn_landing_dust(Group(), _entity())]

    assert len(set(pairs)) == len(pairs), f"the fan repeats a tone and a shape: {pairs}"


def test_a_grain_is_a_handful_of_pixels_and_never_solid() -> None:
    """Three things make a grain a grain rather than a smaller sheet.

    It has no silhouette, it is never opaque, and it dies in less than half the
    time. The ceiling is the one that is easy to get wrong by accident: the top
    of the plane's alpha ladder is full opacity, so a shorter ladder is a
    coarser fade and not a fainter particle. Without a ceiling of its own a
    speck reaches 255, and an opaque speck thrown at the screen is a chip of
    stone rather than a grain of dust.
    """
    grain = GrainParticle((0.0, 0.0), (0.0, 0.0), size=DustGrain.SIZE_RANGE[1])
    peak = 0
    for _ in range(int(DustGrain.TTL * 60)):
        grain.update(1 / 60)
        peak = max(peak, grain.image.get_alpha() or 0)

    assert grain.image.get_width() <= DustGrain.SIZE_RANGE[1], "and it is a speck"
    assert 0 < peak < 255, f"a grain is a haze, not a chip of stone: peaked at {peak}"
    assert DustGrain.TTL < Dust.TTL, "and it is gone before the sheet it came from"


def test_a_landing_throws_more_grit_than_it_does_mass() -> None:
    """The spray is what the eye reads as motion, so it is the majority.

    A kick off a floor throws small particles that travel further than the mass
    does and arrive first. A landing with the ratio the other way round -- a
    handful of grains as an accessory to a heap of sheet -- is a puff of smoke
    with dirt on it, which is the thing this family was added to stop being.
    """
    groups = SpriteGroups()
    spawn_landing_dust(groups.fx_sprites, _entity(), Dust.MIN_FALL_SPEED)
    spawn_landing_grains(groups.fx_sprites, _entity(), Dust.MIN_FALL_SPEED)

    sheets = len([s for s in groups.fx_sprites if s.family == "landing_dust"])
    grains = len([s for s in groups.fx_sprites if s.family == "dust_grain"])
    assert grains > sheets, f"the spray is the majority: {grains} grains to {sheets} sheets"
    assert grains <= FX_FAMILY_BUDGETS["dust_grain"], "and it fits the family budget"


def test_the_trail_plume_turns_over_before_it_fades() -> None:
    """A mark that is still climbing as it dies is a plume, not a trail.

    A puff kicked at ``v0`` against ``GRAVITY`` turns over after ``v0 /
    GRAVITY`` seconds, so the top of the kick has to stay under ``GRAVITY *
    TTL`` or the tallest of the burst is still rising at the moment it fades.
    Measured rather than argued: at a top of eighty-eight the plume sits
    twenty-two pixels off the floor and one of the last two puffs alive is
    still climbing, which reads as smoke off a fire -- the reading these two
    numbers were pulled down from once already.

    So this is arithmetic rather than taste, which makes it the one number in
    the trail a later pass cannot quietly raise.
    """
    ceiling = DashDust.GRAVITY * DashDust.BURST_TTL
    assert DashDust.KICK[1] <= ceiling, (
        f"the burst peaks at {DashDust.KICK[1] / DashDust.GRAVITY:.2f}s and lives "
        f"{DashDust.BURST_TTL}s: it dies mid-climb"
    )
    tick_ceiling = DashDust.GRAVITY * DashDust.TICK_TTL
    assert tick_ceiling >= DashDust.TICK_KICK, (
        f"and the tick peaks at {DashDust.TICK_KICK / DashDust.GRAVITY:.2f}s against "
        f"a {DashDust.TICK_TTL}s life"
    )


def test_the_trail_rides_high_enough_to_be_dust_and_low_enough_to_be_a_trail() -> None:
    """The other side of the same pair, so the fix above cannot be a no-op.

    A ceiling is only worth having if there is a floor: a kick low enough to
    turn over cleanly but also low enough to keep the ribbon on the floor
    satisfies the test above and is the skid this pass was asked to change.
    The claim is about the peak against the fighter rather than about the
    numbers, because the numbers are the thing being set.

    The upper bound is measured against the *drawn sheet* rather than against a
    constant, which is what lets it move with the ladder instead of being an
    obstacle. What the player sees at the top of the plume is the centre's peak
    plus half the sheet's own height at its widest step, and the thing that has
    to stay true is that this is under the fighter -- a plume taller than he is
    has come off the floor and become weather.

    It was a flat twenty-four pixels, which is half a fighter's height and no
    more; the trail was then asked to propagate further upward, and the bound
    moved with it. Deriving it keeps the next raise honest: growing the sheet
    now costs against the same ceiling rather than sliding past it.
    """
    burst = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.BURST_RADIUS)
    tick = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.TICK_RADIUS)
    fighter_height = 48.0

    burst_top = DashDust.KICK[1] ** 2 / (2.0 * DashDust.GRAVITY) + burst.ladder[-1].get_height() / 2
    tick_top = DashDust.TICK_KICK**2 / (2.0 * DashDust.GRAVITY) + tick.ladder[-1].get_height() / 2

    assert tick_top >= 6.0, f"the ribbon has to leave the floor: {tick_top:.1f}px"
    assert burst_top <= fighter_height, (
        f"and the plume stays under the fighter it came off: {burst_top:.1f}px "
        f"against a {fighter_height:.0f}px fighter"
    )
    assert burst_top > tick_top, (
        "the shove throws higher than the path it leaves behind: "
        f"{burst_top:.1f} against {tick_top:.1f}px"
    )


def test_the_dash_trail_carries_no_ink_rim() -> None:
    """The block gave its rim up for the same reason, and so does the trail.

    A mid-grey outline at one pixel per world unit turns a mark into a drawn
    shape with nothing light about it. The landing sheet can afford a rim
    because it sits on the ground against tiles; the trail hangs on open air,
    where a rim is a grey outline drawn around a light mark. So the two tones
    present are the body and the lit rim, and neither ``dust_deep`` nor the
    shadow is among them.
    """
    puff = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.BURST_RADIUS)

    tones = _tones(puff.ladder[0])

    assert tuple(FXColors.dust_deep) not in tones, "the trail is rimless"
    assert tuple(FXColors.dust_shade) not in tones, "and it has no shadow to stand on"
    assert tuple(FXColors.dust) in tones, "the body is there"
    assert tuple(FXColors.dust_lit) in tones, "and so is the lit rim"
    assert len(tones) == 2, f"two tones is the whole grammar, not {tones}"


def test_the_trails_lit_rim_reads_as_light_rather_than_as_a_shade() -> None:
    """Two tones only work if the gap between them survives magnification.

    The landing sheet separates its light with a rim under it; the trail has
    none, so the whole of its separation is the gap between the two tones, and
    at one pixel per world unit a gap that narrow is two greys that read as
    one.
    """
    gap = sum(light - body for body, light in zip(FXColors.dust, FXColors.dust_lit, strict=True))
    assert gap > 80, f"a lit rim with nothing behind it has to be a real step: {gap}"


def test_the_trail_also_carries_no_disc_of_highlight() -> None:
    """The same construction as the landing sheet, so the same guarantee.

    Held separately because the trail is the mark on screen at the instant of
    the dash, and it is the one that used to be a white cloud: a burst of five
    twelve-pixel balls, each with a pearl set into it, under a stretched
    rectangle.
    """
    for radius in DashDust.BUCKETS:
        for variant in range(DashDust.VARIANTS):
            trail = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=radius, variant=variant)
            _no_solid_block(trail.ladder[-1], FXColors.dust_lit)


def test_the_dash_trail_is_thrown_backwards() -> None:
    """The whole effect is this. Forward, or not thrown, it reads as standing in dust.

    A dash crosses about 88px before it ends, so anything left under the
    fighter by the time the dust is at its peak is already behind him -- but
    only if it was pushed the other way. The puffs are laid at the trailing
    edge of the body and every one of them moves against the direction of
    travel.
    """
    dashing_right = _entity(facing=True)
    dashing_left = _entity(facing=False)
    dashing_left.velocity = pygame.math.Vector2(-1100.0, 0.0)

    right = spawn_dash_dust(Group(), dashing_right, burst=True)
    left = spawn_dash_dust(Group(), dashing_left, burst=True)

    assert right and left
    assert all(puff.velocity.x < 0.0 for puff in right), "a dash to the right throws left"
    assert all(puff.velocity.x > 0.0 for puff in left), "and the other way for a dash left"
    assert all(puff.rect.centerx < dashing_right.hitbox.centerx for puff in right), (
        "and the burst is laid behind the fighter, not under him"
    )
    assert all(puff.rect.centerx > dashing_left.hitbox.centerx for puff in left), (
        "behind a fighter dashing the other way too"
    )


def test_the_dash_trail_follows_the_velocity_and_not_the_facing() -> None:
    """A dash resolves its direction in three steps, and only the velocity knows all three.

    It is the move axis captured when the button went down, then the live
    input, then the facing. A fighter can dash left while facing right, and a
    trail thrown off the facing would then be thrown along the direction of
    travel -- which is the opposite of a trail.
    """
    entity = _entity(facing=True)
    entity.velocity = pygame.math.Vector2(-1100.0, 0.0)

    puffs = spawn_dash_dust(Group(), entity, burst=True)

    assert puffs
    assert all(puff.velocity.x > 0.0 for puff in puffs), "a dash left throws right"


def test_the_dash_trail_falls_back_to_the_facing_with_no_velocity() -> None:
    """An entity in a dash state and standing still is not a real dash, but it happens.

    The spawner takes whatever the caller holds, and an entity that has a dash
    state and no movement to read would otherwise throw its whole burst in one
    direction chosen by nothing. The facing is the only answer available, and
    a wrong trail is better than a dust cloud sprayed sideways.
    """
    entity = _entity(facing=False)
    entity.velocity = pygame.math.Vector2(0.0, 0.0)

    puffs = spawn_dash_dust(Group(), entity, burst=True)

    assert puffs
    assert all(puff.velocity.x > 0.0 for puff in puffs), "no velocity, so it falls back"


def test_the_dash_trail_burst_is_bigger_than_the_puffs_that_extend_it() -> None:
    """One shove and a ribbon, or nothing reads as an impact at all.

    If the ticks were the size of the burst the trail would be a uniform
    stripe with no front, and the frame the dash happens on -- the only frame
    the player is looking at the movement -- would carry no more weight than
    the ones after it.
    """
    burst = spawn_dash_dust(Group(), _entity(), burst=True)
    tick = spawn_dash_dust(Group(), _entity())

    assert len(burst) == DashDust.BURST_COUNT
    assert len(tick) == DashDust.TICK_COUNT
    assert max(puff.radius for puff in burst) > max(puff.radius for puff in tick)
    assert max(puff.ladder[-1].get_width() for puff in burst) > max(
        puff.ladder[-1].get_width() for puff in tick
    ), "and the bigger puff is still growing when it dies"


def test_the_dash_trail_evaporates_behind_the_fighter() -> None:
    """The dust has to still be there after the dash ends, or it is debris.

    A dash is 0.08s and the trail is 0.4s to 0.6s. If the puffs died with the
    dash they would read as something the fighter scattered rather than as
    the movement itself, which is the difference the effect exists to make.
    """
    puffs = spawn_dash_dust(Group(), _entity(), burst=True)

    assert min(puff.ttl for puff in puffs) > 0.3, "the trail outlives the dash"


def test_the_trail_puffs_are_laid_along_the_path_and_not_dragged_back() -> None:
    """The ticks are dust left lying down, not dust still being thrown.

    Throwing the ticks as hard as the burst is the difference between a
    ribbon along 88px of path and one mass at the start of it: every tick is
    dragged back into the cloud that threw it, and the trail the player is
    meant to see the movement leave behind collapses into a single blob
    sitting on the frame the dash happened.
    """
    burst = spawn_dash_dust(Group(), _entity(), burst=True)
    tick = spawn_dash_dust(Group(), _entity())

    assert DashDust.TICK_THROW < DashDust.THROW / 4, "a tick is laid, not thrown"
    assert max(puff.velocity.x for puff in tick) > -DashDust.THROW, (
        "and no tick travels at the burst's speed"
    )
    assert max(abs(puff.velocity.x) for puff in burst) > 2 * max(
        abs(puff.velocity.x) for puff in tick
    )


def test_the_dash_trail_settles_instead_of_climbing_off_the_floor() -> None:
    """The trail is a mark on the ground the fighter left, not smoke off the spot.

    The landing puff's gravity is a negative ``RISE``, which accelerates it
    off the floor for its whole life. A trail cannot work that way: still
    climbing half a second later, the dust reads as a plume hanging where the
    dash began rather than as the path someone took across it.

    What "settles" means here is bounded rather than returning -- drag stops
    the velocity long before gravity would bring it down, so the puff rises,
    turns over and holds. What matters is that the rise has a ceiling.
    """
    assert DashDust.GRAVITY > 0.0, "a kicked puff is not propelled upward forever"
    puff = DashDustParticle((0.0, 0.0), (0.0, -90.0), radius=DashDust.BURST_RADIUS)

    ground = puff.pos.y
    for _ in range(int(puff.max_ttl * 60)):
        puff.update(1 / 60)

    risen = ground - puff.pos.y
    assert 0.0 < risen < 40.0, f"a puff that rises {risen}px is a plume, not a trail"


def test_the_dash_trail_fades_up_faster_than_the_block_ring() -> None:
    """The fighter crosses most of the ribbon before a slow ramp would show it.

    The block can afford 0.08s because it stands still while the player reads
    it. The trail cannot: at 1100 px/s the fighter is most of the way down it
    in the time the ring takes to reach full opacity, so the dust is still
    fading up where he already is not.
    """
    assert DashDust.FADE_IN < FxGuard.ARC_FADE_IN


_RUN = FootstepDust.TIER[PlayerState.RUN.value]
"""The row a footstep spawner is handed when the test only cares about the mark.

Every spawn call in this file passes it, because ``spawn_footstep_dust`` takes
the tier as a required argument: the emitter resolves the gait and the painter
does not guess it. The tests below are about where the mark lands and which way
it is thrown, not about which gait it came from, so they take the run row once
here rather than repeating it.
"""


def test_a_footstep_carries_no_ink_rim_either() -> None:
    """Same rule as the trail, and the same argument, at a smaller size.

    The rim is the rule with the exception, not the rule. It is kept only where
    a mark sits against the tiles and its edge is doing the work -- the landing
    sheet. A footstep is the trail's substance at two-thirds the size, thrown
    up off the floor and gone in three tenths of a second, and a mid-grey
    outline around it would be a grey outline drawn around a light mark.

    At this size the rim would also be most of the mark, which is the other
    reason it has to go: the two tones have to carry the whole read here.
    """
    puff = FootstepDustParticle((0.0, 0.0), (0.0, 0.0))

    tones = _tones(puff.ladder[0])

    assert tuple(FXColors.dust_deep) not in tones, "a footstep is rimless"
    assert tuple(FXColors.dust_shade) not in tones, "and it has no shadow to stand on"
    assert len(tones) == 2, f"two tones is the whole grammar, not {tones}"


def test_a_footstep_shares_the_trails_ladder_rather_than_building_its_own() -> None:
    """The busiest mark in the plane cannot afford frames nobody else uses.

    The ladder is keyed on radius bucket, tone and silhouette, and a footstep's
    radius lands in the same buckets as a dash tick's -- so a ladder of its own
    would double the frames in the table for a mark that is the same cloud at a
    smaller size. This is the assertion that the inheritance is doing the work
    rather than the two classes merely sharing a shape recipe.
    """
    for radius in (FootstepDust.RADIUS, DashDust.TICK_RADIUS):
        step = FootstepDustParticle((0.0, 0.0), (0.0, 0.0), radius=radius, tint=0.1, variant=2)
        trail = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=radius, tint=0.1, variant=2)
        assert all(a is b for a, b in zip(step.ladder, trail.ladder, strict=True)), (
            f"the same frames at radius {radius}, not two copies"
        )


def test_a_footstep_draws_the_smallest_sheet_the_ladder_holds() -> None:
    """And there is nothing below it, which is also why its size cannot be a knob.

    The trail's ladder is keyed on the discrete radii in ``DashDust.BUCKETS``,
    so a request is drawn at the entry nearest it and every radius under the
    second bucket produces the same pixels. ``FootstepDust.RADIUS`` sits inside
    the first one: the footstep is the smallest mark the plane can draw.

    That is worth pinning twice over, because the obvious next idea -- scale the
    mark by ground speed, so ``walk_slow`` throws a smaller step than a run --
    cannot work at this size. The number would move and the screen would not.
    What says how fast the fighter is going is the cadence, which is already
    doing it: the same mark laid tighter and tighter as he speeds up.
    """
    edge = (DashDust.BUCKETS[0] + DashDust.BUCKETS[1]) / 2.0 - 0.5
    widest = FootstepDustParticle((0.0, 0.0), (0.0, 0.0), radius=edge)
    smallest = FootstepDustParticle((0.0, 0.0), (0.0, 0.0), radius=0.0)

    assert widest.ladder[-1].get_width() == smallest.ladder[-1].get_width(), (
        "everything under the second bucket is one sheet, so a size knob is invisible"
    )
    step = FootstepDustParticle((0.0, 0.0), (0.0, 0.0))
    bigger = FootstepDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.BUCKETS[1])

    assert step.ladder[-1].get_width() < bigger.ladder[-1].get_width(), (
        "and the mark grows only at a bucket boundary"
    )


def test_a_footstep_turns_over_before_it_fades() -> None:
    """A mark that is still climbing as it dies is a plume, not a footstep.

    The same arithmetic as the trail's, and the same reason it is arithmetic:
    this is the one number a later pass cannot quietly raise. A step is born at
    the floor and has to be back at it, because it is a mark *on* the ground.
    """
    ceiling = FootstepDust.GRAVITY * FootstepDust.TTL
    assert FootstepDust.KICK[1] <= ceiling, (
        f"the tallest puff peaks at {FootstepDust.KICK[1] / FootstepDust.GRAVITY:.2f}s and "
        f"lives {FootstepDust.TTL}s: it dies mid-climb"
    )


def test_a_footstep_leaves_the_floor_barely_at_all() -> None:
    """The other side of the ceiling above, so lowering it cannot be the whole fix.

    A kick low enough to turn over cleanly and low enough to never leave the
    floor satisfies the test above and draws nothing. A footstep has to arc
    two or three pixels to read as thrown rather than pasted.
    """
    peak = FootstepDust.KICK[1] ** 2 / (2.0 * FootstepDust.GRAVITY)
    assert peak >= 1.5, f"the mark has to leave the ground to read as dust: {peak:.2f}px"
    assert peak < DashDust.TICK_KICK**2 / (2.0 * DashDust.GRAVITY), (
        "and it stays well under the ribbon's arc: it is a foot, not a shove"
    )


def test_a_footstep_is_laid_behind_the_heel_and_thrown_backwards() -> None:
    """The whole effect is this, twice: where it is born and which way it goes.

    A mark born under the fighter is painted under him and spends its life
    invisible; a mark thrown forwards is a mark the fighter is walking into
    rather than one he left. So the anchor is his trailing edge and every puff
    moves against the direction of travel.
    """
    right = spawn_footstep_dust(Group(), _entity(facing=True), foot=False, tier=_RUN)
    left_entity = _entity(facing=False)
    left_entity.velocity = pygame.math.Vector2(-200.0, 0.0)
    left = spawn_footstep_dust(Group(), left_entity, foot=False, tier=_RUN)

    assert right and left
    assert all(puff.velocity.x < 0.0 for puff in right), "a step right is thrown left"
    assert all(puff.velocity.x > 0.0 for puff in left), "and the other way for a step left"
    assert all(puff.rect.centerx < right[0].pos.x for puff in right), (
        "and laid behind the heel rather than under him"
    )


def test_a_footstep_follows_the_velocity_and_not_the_facing() -> None:
    """A fighter turns before it finishes a step, and the mark goes where the feet go.

    Same argument as the trail's: the facing is where the fighter is looking,
    which a strafe, a knockback and a fighter sliding backwards all make a lie
    about. Only the velocity is the direction the fighter is travelling.
    """
    entity = _entity(facing=True)
    entity.velocity = pygame.math.Vector2(-200.0, 0.0)

    puffs = spawn_footstep_dust(Group(), entity, foot=False, tier=_RUN)

    assert puffs
    assert all(puff.velocity.x > 0.0 for puff in puffs), "moving left, thrown right"


def test_a_footstep_is_the_trails_own_cloud_at_a_third_of_the_cadence() -> None:
    """Same sheet as a dash tick, and it is not a problem, because of *when*.

    Both land in the ladder's first bucket, so a footstep is not a smaller mark
    than the trail's ticks -- it is the same cloud with a different schedule.
    What separates them on screen is that the dash is one shove and five ticks
    inside a sixth of a second, and a walk lays the same cloud twelve times a
    second forever, low and short-lived. The size is the trail's; the reading
    is not.

    Held as a fact rather than left to be discovered, because the reflex on
    seeing a footstep the size of a dash tick is to shrink the number, and the
    number is not what draws it.
    """
    tick = DashDustParticle((0.0, 0.0), (0.0, 0.0))

    assert DashDust.BUCKETS[1] > DashDust.TICK_RADIUS, "and the tick is in the same bucket"
    assert (
        tick.ladder[-1].get_width()
        == FootstepDustParticle((0.0, 0.0), (0.0, 0.0)).ladder[-1].get_width()
    )
    assert FootstepDust.TTL < DashDust.TICK_TTL, "but the step is gone sooner"
    assert FootstepDust.KICK[1] < DashDust.TICK_KICK, "and it never leaves the floor"


def test_a_footstep_is_the_same_mark_at_every_gait_and_that_is_deliberate() -> None:
    """The two tiers differ in cadence and spread and in nothing else.

    Size cannot be one of the knobs: the ladder is drawn at the nearest of its
    discrete radii, so every request under the second bucket is the same sheet
    (see the test above). Height should not be one either -- a foot is a foot,
    and a run's landing no higher than a walk's is the same two pixels of floor
    being disturbed faster.

    So the tiers are the two things the eye reads as *gait* rather than as
    loudness, and this holds the rest still: the sheet, the kick and the life are
    one number each for the whole effect, and no tier row may grow a third knob
    to carry a difference the ladder cannot show.
    """
    assert set(FootstepDust.TIER) == {PlayerState.WALK.value, PlayerState.RUN.value}
    assert set(FootstepDust.SILENT) == {PlayerState.WALK_SLOW.value}
    for tier in FootstepDust.TIER.values():
        assert len(tier) == 2, f"a tier row is cadence and spread and nothing else: {tier}"
        assert tier.step_distance > 0.0


def test_a_footstep_spends_the_grit_budget_and_not_its_own() -> None:
    """The spray is what makes the mark read as dust, and it is the cheaper half.

    A plane already full sheds the grit before it sheds the comb, which is the
    arrangement ``DustGrain`` sets up for the landing: losing the spray costs
    the effect a little of its read, losing the mark costs the movement its
    only trace.
    """
    grains = spawn_footstep_grains(Group(), _entity())

    assert grains, "a step carries spray as well as mass"
    assert {grain.family for grain in grains} == {"dust_grain"}
    assert len(grains) == FootstepDust.GRAINS
    assert FX_FAMILY_BUDGETS["footstep_dust"] > FootstepDust.GRAINS, (
        "and the mark it is puncturing is not the smaller half of the two"
    )


def test_the_block_ring_stands_on_the_side_the_attack_came_from() -> None:
    """A ring off to one side of the fighter reads as a block.

    A ring in the middle of the body would be a status icon, and a fan of
    thrown particles would be an explosion: only the offset says the guard
    took the hit rather than being turned into it.
    """
    right = spawn_guard_arc(Group(), _entity(facing=True))
    left = spawn_guard_arc(Group(), _entity(facing=False))

    assert isinstance(right, ShieldArcParticle)
    assert right is not None and left is not None
    assert right.side == 1.0
    assert left.side == -1.0
    assert right.pos.x > _entity().hitbox.centerx
    assert left.pos.x < _entity().hitbox.centerx
    assert right.image.get_size() == left.image.get_size()


def test_the_block_ring_is_one_hollow_fine_stroke() -> None:
    """A hairline ring, and nothing of the inked band it used to be.

    The rim was a five-pixel comic-panel outline, which at a 40-unit fighter
    is a heavy drawn shape rather than a flash of light.
    """
    ring = spawn_guard_arc(Group(), _entity())
    assert ring is not None
    image = ring.image
    width, height = image.get_size()
    middle_y = height // 2

    def lit(x: int) -> bool:
        return bool(image.get_at((x, middle_y))[3])

    lit_columns = [x for x in range(width) if lit(x)]
    opaque = sum(1 for y in range(height) for x in range(width) if image.get_at((x, y))[3])

    assert lit_columns[0] < width // 2 - 4, "a ring is hollow in the middle"
    assert lit_columns[-1] > width // 2 + 4
    assert not lit(width // 2)
    filled = width * height
    assert opaque < filled // 3, "and it is a stroke, not a filled disc"
    assert width == height


def test_the_bright_kick_only_covers_the_side_the_hit_landed_on() -> None:
    """The direction is what makes the ring read as a block.

    A plain ring of any colour says something happened; a ring brighter on
    one side says the guard turned it away.
    """
    right = spawn_guard_arc(Group(), _entity(facing=True))
    left = spawn_guard_arc(Group(), _entity(facing=False))
    assert right is not None and left is not None

    def kick_columns(image: pygame.Surface) -> set[int]:
        width, height = image.get_size()
        return {
            x
            for x in range(width)
            if any(image.get_at((x, y))[:3] == Colors.off_white for y in range(height))
        }

    forward = kick_columns(right.image)
    backward = kick_columns(left.image)
    half = right.image.get_width() / 2

    assert forward and backward, "both sides need a kick to be a kick"
    assert min(forward) > half, "the kick is on the side the guard faces"
    assert max(backward) < half


def test_a_perfect_block_is_the_same_ring_in_gold() -> None:
    block = spawn_guard_arc(Group(), _entity())
    parried = spawn_guard_arc(Group(), _entity(), parried=True)

    assert block is not None and parried is not None
    assert parried.image.get_size() == block.image.get_size(), "same ring, same size"
    assert parried.body == FXColors.parry_spark
    assert parried.body != block.body


def test_a_block_spawns_the_ring_and_no_particles() -> None:
    """No thrown particles on a block at all.

    They were the last carrier of a star shape into every exchange, and the
    ring is the whole silhouette.
    """
    group = Group()

    spawn_guard_arc(group, _entity())

    assert len(group) == 1
    assert not any(isinstance(sprite, OrbitParticle) for sprite in group)


def test_only_the_dizzy_state_produces_stars() -> None:
    """The four-pointed star is built in one place, and it is this one.

    It used to be the guard and parry spark shape too, which put six gold
    stars on screen on every exchange in a fight.
    """
    stars = fx.spawn_dizzy_stars(Group(), _entity())
    shatter = fx.spawn_shatter_arc(Group(), _entity())

    assert stars and all(isinstance(star, OrbitParticle) for star in stars)
    assert shatter is not None
    assert not any(isinstance(step, OrbitParticle) for step in shatter.steps)


def test_the_ring_stands_where_the_block_landed() -> None:
    """The contact point is what the guard event reports, so it is what we draw.

    Standing the ring in front of the defender was a guess: it put the mark
    at the middle of the body rather than where the hit was absorbed, and it
    ignored the one piece of data the combat system had already computed.
    """
    entity = _entity(facing=True)
    contact = (entity.hitbox.right + 6.0, entity.hitbox.centery - 4.0)

    arc = spawn_guard_arc(Group(), entity, contact=contact)

    assert arc is not None
    assert arc.pos.x == pytest.approx(contact[0])
    assert arc.pos.y == pytest.approx(contact[1])
    assert arc.side == 1.0


def test_a_back_turned_block_puts_the_ring_where_the_hit_came_from() -> None:
    """The side comes from the contact, not from which way the guard looks.

    Reading ``facing_right`` opened the ring towards the defender's own
    facing, so a guard blocking a hit from behind got it on the wrong side of
    the body -- the one case where the mark contradicted the event.
    """
    entity = _entity(facing=True)
    behind = (entity.hitbox.left - 6.0, entity.hitbox.centery)

    arc = spawn_guard_arc(Group(), entity, contact=behind)

    assert arc is not None
    assert arc.side == -1.0, "the ring opens away from the body, towards the hit"


def test_a_clash_spawns_no_guard_ring() -> None:
    """Two weapons meeting is not a block, and used to draw one.

    The event branch was an ``else``, so anything the loop did not name --
    and a clash is what it did not name -- got the block's arc. Unreachable
    while no attack declares clash data, and a wrong mark the day one does.
    """
    from src.core.level.systems.contact_system import GuardEvent
    from src.core.level.systems.gameplay_loop import GameplayLoop

    entity = _entity()
    group = Group()
    loop = GameplayLoop(camera_system=SimpleNamespace(add_trauma=lambda _amount: None))

    for kind in ("clash", "stun"):
        loop._spawn_fx_for_event(GuardEvent(kind, entity), group)

    assert len(group) == 0


def test_a_break_breaks_the_ring_rather_than_throwing_shards() -> None:
    """The failing guard is the same shield on the way out, not a new effect.

    It used to throw a fan of triangles from the middle of the fighter, which
    said nothing about the guard at all.
    """
    group = Group()

    shatter = fx.spawn_shatter_arc(group, _entity())

    assert shatter is not None
    assert len(group) == 1
    assert isinstance(group.sprites()[0], ShatterArcParticle)


def test_the_ring_starts_whole_and_breaks_into_pieces() -> None:
    """A circle breaking, not debris that happened to be round.

    The first step has to carry the ring at its own radius, and the last has
    to have moved off it: that is the difference between the block's circle
    failing and a burst of marks near the fighter.
    """
    shatter = fx.spawn_shatter_arc(Group(), _entity(facing=True))
    assert shatter is not None
    radius = snap(FxGuard.SHARD_RADIUS)

    def at_ring_radius(step: int) -> int:
        """How many angles still carry a pixel on the ring's own radius."""
        image = shatter.steps[step]
        centre = image.get_width() / 2.0
        return sum(
            1
            for degree in range(360)
            if any(
                image.get_at(
                    (
                        snap(centre + (radius + offset) * math.cos(math.radians(degree))),
                        snap(centre + (radius + offset) * math.sin(math.radians(degree))),
                    )
                )[3]
                for offset in (-1.0, 0.0, 1.0)
            )
        )

    assert at_ring_radius(0) >= 300, "the first step is still a circle"
    assert at_ring_radius(-1) < at_ring_radius(0), "and the last has come off it"

    spread = 0
    for step in range(len(shatter.steps)):
        image = shatter.steps[step]
        centre = image.get_width() / 2.0
        spread += sum(
            1
            for degree in range(0, 360, 3)
            for offset in range(radius + 1, image.get_width() // 2)
            if image.get_at(
                (
                    snap(centre + offset * math.cos(math.radians(degree))),
                    snap(centre + offset * math.sin(math.radians(degree))),
                )
            )[3]
        )
    assert spread > 0, "and the pieces have to leave the ring behind"


def test_the_pieces_fly_furthest_from_the_side_that_failed() -> None:
    """The break radiates from the wound, so the facing side leads.

    Both halves of the silhouette break, but not evenly: the fragments near
    the side the hit landed on travel further than the ones at the back.
    """
    shatter = fx.spawn_shatter_arc(Group(), _entity(facing=True))
    assert shatter is not None
    image = shatter.steps[-1]
    width = image.get_width()
    centre = width / 2.0

    limit = width // 2 - 1

    def reach(side: str) -> int:
        """The furthest radius still drawn on that half of the ring."""
        best = 0
        for degree in range(360):
            facing_right = math.cos(math.radians(degree)) >= 0
            if (side == "front") != facing_right:
                continue
            for radius in range(snap(FxGuard.SHARD_RADIUS), limit):
                if image.get_at(
                    (
                        snap(centre + radius * math.cos(math.radians(degree))),
                        snap(centre + radius * math.sin(math.radians(degree))),
                    )
                )[3]:
                    best = max(best, radius)
                    break
        return best

    assert reach("front") > reach("back"), "the fragments on the hit side have to travel further"


def test_a_family_cap_holds_even_under_the_global_one() -> None:
    """A fourteen-spark parry used to starve the rest of the plane out."""
    group = Group()
    entity = _entity()
    cap = FX_FAMILY_BUDGETS["landing_dust"]

    spawned = [spawn_landing_dust(group, entity, Dust.MIN_FALL_SPEED * 2) for _ in range(cap + 4)]

    assert any(spawned), "the effect has to land at all"
    assert len(group) <= cap, "the cap is a ceiling, not a threshold"
    assert len(group) < MAX_FX_SPRITES, "well under the global cap"
    assert not spawned[-1], "and by the end the family is refused"

    # The cap holds below the budget, not exactly at it: a fan of
    # ``Dust.COUNT`` is refused whole rather than half-landed, so the last
    # accepted call leaves a gap under the number.


def test_the_global_cap_still_wins_over_the_family_one() -> None:
    group = Group()
    for _ in range(MAX_FX_SPRITES):
        group.add(DustParticle((0.0, 0.0), (0.0, 0.0)))

    assert spawn_landing_dust(group, _entity(), Dust.MIN_FALL_SPEED * 2) == []
    assert spawn_dizzy_vortex(group, _entity()) is None


def test_the_dizzy_swirl_and_the_stars_do_not_share_a_place() -> None:
    """They used to be drawn on top of each other over the head."""
    entity = SimpleNamespace(hitbox=pygame.FRect(100, 100, 40, 48), parry_stun_duration=1.0)
    stars = fx.spawn_dizzy_stars(Group(), entity)
    vortex = fx.spawn_dizzy_vortex(Group(), entity)

    assert stars and vortex is not None
    assert vortex.pos.y > entity.hitbox.bottom - 6.0, "the swirl is at the feet"
    assert all(star.orbit_center.y < entity.hitbox.top for star in stars), (
        "and the stars circle the head"
    )
