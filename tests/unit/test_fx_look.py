"""FX behaviour the visual pass changed: layering, contact points and budgets.

These are the properties a screenshot cannot show and a frame time cannot
reveal: which plane a mark is painted in, where a burst is thrown from, and
that a big burst cannot starve the effects that have to keep animating.
"""

import os
from types import SimpleNamespace

import pygame
import pytest
from pygame.sprite import Group

from src.core import fx
from src.core.colors import FXColors
from src.core.display.framing import DEFAULT_FRAMING
from src.core.display.viewport import Viewport
from src.core.fx import (
    FX_FAMILY_BUDGETS,
    MAX_FX_SPRITES,
    DustParticle,
    GuardFlashParticle,
    OrbitParticle,
    SparkParticle,
    spawn_dash_trail,
    spawn_dash_wind,
    spawn_guard_flash,
    spawn_impact_decal,
    spawn_landing_dust,
)
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import Renderer
from src.core.settings import Dust
from src.core.sprite_groups import SpriteGroups


@pytest.fixture(scope="module", autouse=True)
def _display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((640, 480))


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
    assert SparkParticle((0.0, 0.0), (0.0, 0.0), (255, 255, 255)).behind is False


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
    spark = SparkParticle((300.0, 300.0), (10.0, 10.0), (255, 200, 60))
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


def test_the_guard_wedge_opens_away_from_the_side_the_attack_came_from() -> None:
    right = spawn_guard_flash(Group(), _entity(facing=True))
    left = spawn_guard_flash(Group(), _entity(facing=False))

    assert isinstance(right, GuardFlashParticle)
    assert right is not None and left is not None
    assert right.side == 1.0
    assert left.side == -1.0
    assert right.pos.x > _entity().hitbox.centerx
    assert left.pos.x < _entity().hitbox.centerx
    assert right.steps[-1].get_width() == left.steps[-1].get_width()


def test_a_break_throws_shards_and_a_block_throws_chips() -> None:
    """Guard and break differ by silhouette, not only by colour.

    Colour alone does not survive a still frame, or a bright background.
    """
    entity = _entity()
    guard = fx.spawn_guard_spark(Group(), entity)
    broken = fx.spawn_break_burst(Group(), entity)

    assert {spark.shape for spark in guard} == {"chip"}
    assert {spark.shape for spark in broken} == {"shard"}
    assert max(spark.size for spark in broken) > max(spark.size for spark in guard)
    assert {tuple(spark.ink) for spark in broken} == {tuple(FXColors.ink_warm)}


def test_no_block_spark_is_shaped_like_a_star() -> None:
    """The stars belong to the dizzy state and to nothing else.

    A four-pointed sparkle thrown out of a block is a star flying out of a
    block, and a parry is the most repeated event in a fight: the one effect
    that must not look like the dizzy one is the one on every exchange.
    """
    entity = _entity()

    for sparks in (
        fx.spawn_guard_spark(Group(), entity),
        fx.spawn_parry_burst(Group(), entity),
        fx.spawn_break_burst(Group(), entity),
    ):
        assert sparks
        for spark in sparks:
            assert spark.shape in ("chip", "shard")
            assert not isinstance(spark, OrbitParticle)

    stars = fx.spawn_dizzy_stars(Group(), entity)
    assert all(isinstance(star, OrbitParticle) for star in stars)


def test_a_parry_is_the_block_effect_in_gold_and_nothing_more() -> None:
    """The same burst in another colour, to the spark.

    A parry is the most repeated event in a fight, and it used to throw twice
    the sparks, throw them longer, and wash the whole frame: three times the
    screen coverage of the thing it is a bigger version of.
    """
    parry_spec, block_spec = fx.PARRY_BURST, fx.GUARD_BURST
    geometry = ("count", "speed", "cone", "tilt", "shape", "size", "elongation")

    for field in geometry:
        assert getattr(parry_spec, field) == getattr(block_spec, field), (
            f"a parry must not change the {field} of a block"
        )
    assert parry_spec.colors != block_spec.colors
    assert parry_spec.core != block_spec.core

    entity = _entity()
    block = fx.spawn_guard_spark(Group(), entity)
    parried = fx.spawn_parry_burst(Group(), entity)

    assert len(parried) == len(block)
    assert {spark.shape for spark in parried} == {spark.shape for spark in block}
    assert FXColors.parry_spark in {tuple(spark.color) for spark in parried}
    assert FXColors.parry_spark not in {tuple(spark.color) for spark in block}


def test_the_parry_wedge_is_the_block_wedge_in_gold() -> None:
    block = spawn_guard_flash(Group(), _entity())
    parried = spawn_guard_flash(Group(), _entity(), parried=True)

    assert block is not None and parried is not None
    assert parried.steps[-1].get_size() == block.steps[-1].get_size(), "same wedge, same size"
    assert parried.body == FXColors.parry_spark
    assert parried.body != block.body


def test_the_guard_wedge_opens_by_stepping_through_prebuilt_sizes() -> None:
    """A wedge is directional; a redrawn fan is an explosion at the middle."""
    flash = spawn_guard_flash(Group(), _entity())
    assert flash is not None
    first = flash.image

    flash.update(flash.max_ttl * 0.6)

    assert flash.image is not first
    assert len({step.get_width() for step in flash.steps}) == len(flash.steps)
    assert flash.image.get_width() > first.get_width()


def test_a_family_cap_holds_even_under_the_global_one() -> None:
    """A fourteen-spark parry used to starve the dash trail out of existence."""
    group = Group()
    entity = _entity()
    cap = FX_FAMILY_BUDGETS["dash_trail"]

    spawned = [spawn_dash_trail(group, entity) for _ in range(cap + 4)]

    assert sum(1 for trail in spawned if trail is not None) == cap
    assert len(group) == cap
    assert len(group) < MAX_FX_SPRITES, "well under the global cap"


def test_the_global_cap_still_wins_over_the_family_one() -> None:
    group = Group()
    for _ in range(MAX_FX_SPRITES):
        group.add(DustParticle((0.0, 0.0), (0.0, 0.0)))

    assert spawn_dash_trail(group, _entity()) is None
    assert spawn_dash_wind(group, _entity()) == []


def test_the_wind_lines_are_torn_off_in_front_of_the_dash() -> None:
    entity = _entity(200.0, 200.0)
    lines = spawn_dash_wind(Group(), entity)

    assert len(lines) == fx.DASH_WIND_LINES
    for line in lines:
        assert line.pos.x > entity.hitbox.centerx, "ahead of the dasher"
        assert line.velocity.x < 0.0, "and the air it tears off goes backwards"


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
