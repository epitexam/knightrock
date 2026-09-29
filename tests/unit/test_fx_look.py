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
from src.core.colors import Colors, FXColors
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.viewport import Viewport
from src.core.fx import (
    FX_FAMILY_BUDGETS,
    MAX_FX_SPRITES,
    DashDustParticle,
    DustParticle,
    OrbitParticle,
    ShatterArcParticle,
    ShieldArcParticle,
    spawn_dash_dust,
    spawn_dizzy_vortex,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawners,
)
from src.core.fx.draw import snap
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.settings import DashDust, Dust, FxGuard
from src.core.sprite_groups import SpriteGroups


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


def test_a_puff_is_a_cloud_and_not_a_ball() -> None:
    """One disc reads as a ball. The silhouette has to be lumpy to read as dust.

    The lobes are what make it a cloud, and what the ink rim follows, so this
    is a claim about the outline: a silhouette as wide as it is tall, with
    nothing pushing out to one side, is the shape the puff had before the
    lobes existed.

    The first step is squashed, because dust leaves the ground flat and
    rounds off as it rises, so the claim is on the last step -- the one the
    player sees as the puff drifts up.
    """
    puff = DustParticle((0.0, 0.0), (0.0, 0.0), radius=8.0)

    flat = _ink_extent(puff.ladder[0])
    open_ = _ink_extent(puff.ladder[-1])
    assert flat[0] > flat[1], f"a puff leaves the ground flat: {flat}"
    assert open_[0] > open_[1], f"and stays wider than tall as it opens: {open_}"
    assert puff.ladder[-1].get_width() > puff.ladder[0].get_width(), "the billow widens"


def test_the_puff_rim_actually_separates_it_from_the_background() -> None:
    """The rim is the DA's reason for inking, so it has to be a real contrast.

    The old one sat 44 units under the body colour. At a one-pixel outline
    that is barely a shade, and against a bright background the cloud lost its
    edge and came out as a smudge -- which is the one thing the ink rule
    exists to prevent.
    """
    puff = DustParticle((0.0, 0.0), (0.0, 0.0), radius=8.0)
    surface = puff.ladder[0]

    tones = {
        tuple(surface.get_at((x, y))[:3])
        for y in range(surface.get_height())
        for x in range(surface.get_width())
        if surface.get_at((x, y))[3]
    }
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


def test_the_dash_trail_carries_no_ink_rim() -> None:
    """The block gave its rim up for the same reason, and so does the trail.

    A mid-grey outline at one pixel per world unit turns a mark into a drawn
    shape with nothing light about it. The landing puff can afford a rim
    because it sits on the ground against tiles; the trail hangs on open air,
    where a rim is a grey outline drawn around a light cloud. So the two tones
    present are the body and the lit lobe, and ``dust_deep`` is not among
    them.
    """
    puff = DashDustParticle((0.0, 0.0), (0.0, 0.0), radius=DashDust.BURST_RADIUS)

    tones = _tones(puff.ladder[0])

    assert tuple(FXColors.dust_deep) not in tones, "the trail is rimless"
    assert tuple(FXColors.dust) in tones, "the body is there"
    assert tuple(FXColors.dust_lit) in tones, "and so is the lit lobe"
    assert len(tones) == 2, f"two tones is the whole grammar, not {tones}"


def test_the_trails_lit_lobe_reads_as_light_rather_than_as_a_shade() -> None:
    """Two tones only work if the gap between them survives magnification.

    The landing puff lifts its lit lobe off the body by 0.3, an 18 unit
    difference, and has a rim to help it. The trail has no rim, so the whole
    separation is the gap between the two tones, and at one pixel per world
    unit a gap that narrow is two greys that read as one.
    """
    gap = sum(light - body for body, light in zip(FXColors.dust, FXColors.dust_lit, strict=True))
    assert gap > 80, f"a lit lobe with no rim behind it has to be a real step: {gap}"


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
