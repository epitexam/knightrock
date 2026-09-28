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
    ScreenFlash,
    ShieldArcParticle,
    SparkParticle,
    spawn_dash_trail,
    spawn_dash_wind,
    spawn_guard_arc,
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


def test_the_guard_arc_faces_the_side_the_attack_came_from() -> None:
    right = spawn_guard_arc(Group(), _entity(facing=True))
    left = spawn_guard_arc(Group(), _entity(facing=False))

    assert isinstance(right, ShieldArcParticle)
    assert right is not None and left is not None
    assert right.side == 1.0
    assert left.side == -1.0
    assert right.pos.x > _entity().hitbox.centerx
    assert left.pos.x < _entity().hitbox.centerx


def test_the_three_bursts_are_told_apart_by_their_shape() -> None:
    """Colour alone does not survive a still frame or a bright background."""
    entity = _entity()
    guard = fx.spawn_guard_spark(Group(), entity)
    parry = fx.spawn_parry_burst(Group(), entity)
    broken = fx.spawn_break_burst(Group(), entity)

    assert {spark.points for spark in guard} == {4}
    assert {spark.points for spark in broken} == {3}, "a break throws shards"
    assert max(spark.size for spark in broken) > max(spark.size for spark in guard)
    assert max(spark.elongation for spark in parry) > max(spark.elongation for spark in guard), (
        "and a parry throws the longest sparks"
    )
    assert {tuple(spark.ink) for spark in broken} == {tuple(FXColors.ink_warm)}


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


def test_the_screen_flash_rises_and_falls_and_clears() -> None:
    flash = ScreenFlash()
    flash.trigger(0.5)

    assert 0 < flash.alpha < 255
    flash.update(fx.SCREEN_FLASH_DURATION + 0.01)

    assert flash.alpha == 0
    assert flash.strength == 0.0


def test_the_screen_flash_is_bounded() -> None:
    flash = ScreenFlash()
    flash.trigger(9.0)
    peak = flash.alpha
    flash.trigger(-3.0)
    assert flash.alpha == 0
    flash.trigger(1.0)
    assert flash.alpha <= peak


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
