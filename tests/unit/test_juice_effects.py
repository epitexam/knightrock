"""Game-feel juice: hit flash, dash afterimages, sweat drops, dust puffs."""

import os
import random
from collections.abc import Iterator
from types import SimpleNamespace

import pygame
import pytest

from src.core.colors import FXColors
from src.core.display.framing import Framing
from src.core.fx import (
    FX_FAMILY_BUDGETS,
    MAX_FX_SPRITES,
    DustParticle,
    StreakParticle,
    SweatParticle,
    dash_direction,
    iter_landing_entities,
    spawn_dash_burst,
    spawn_dash_shockwave,
    spawn_dash_streak,
    spawn_dash_trail,
    spawn_dash_wind,
    spawn_dizzy_stars,
    spawn_dizzy_vortex,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_shatter_arc,
    spawn_sweat_drops,
    spawners,
)
from src.core.level.systems.physics_system import PhysicsSystem
from src.core.rendering.camera import Camera
from src.core.rendering.renderer import (
    DASH_STRETCH_X,
    DASH_STRETCH_Y,
    Renderer,
    dash_frame,
    is_player_dashing,
)
from src.core.settings import Afterimage, Dust, FxDash, HitFlash, Sweat
from src.core.settings import Sweat as SweatSettings
from src.core.sprite_groups import SpriteGroups
from tests.unit.helpers import make_entity


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    """Dummy SDL display so Surfaces render without a window."""
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


def _floor_tile(top: float = 200.0) -> SimpleNamespace:
    box = pygame.FRect(0, top, 400, 64)
    return SimpleNamespace(rect=box, hitbox=box, old_hitbox=box.copy())


# --- Hit flash -----------------------------------------------------------


def test_damage_arms_a_short_white_flash() -> None:
    entity = make_entity(faction="player")

    entity.receive_damage(10.0)

    assert entity.flash_timer == pytest.approx(HitFlash.DURATION)


def test_flash_ticks_down_and_never_enters_snapshots() -> None:
    entity = make_entity(faction="player")
    entity.receive_damage(10.0)

    entity.update(1 / 60)

    assert 0.0 <= entity.flash_timer < HitFlash.DURATION
    snapshot = entity.save_state()
    assert "flash_timer" not in snapshot.extra
    entity.flash_timer = 0.123
    entity.load_state(snapshot)
    assert entity.flash_timer == pytest.approx(0.123)


def test_immune_hit_arms_no_flash() -> None:
    entity = make_entity(faction="player")
    entity.invincibility_timer = 1.0

    result = entity.receive_damage(10.0)

    assert not result.applied
    assert entity.flash_timer == pytest.approx(0.0)


# --- Dash afterimages -----------------------------------------------------


class DashSprite(pygame.sprite.Sprite):
    """Minimal player-like sprite with a switchable state name."""

    def __init__(self, state: str = "dash") -> None:
        super().__init__()
        self.faction = "player"
        self.state_machine = SimpleNamespace(current_state_name=state)
        self.image = pygame.Surface((20, 30))
        self.image.fill((255, 255, 255))
        self.rect = pygame.FRect(10, 10, 20, 30)


def _dashing_player() -> DashSprite:
    return DashSprite(state="dash")


def test_dash_spawns_a_capped_fading_ghost_trail() -> None:
    surface = pygame.Surface((64, 64))
    # zoom=1.0: this test measures the ghost in world-sized pixels.
    camera = Camera(Framing(float(64), float(64)))
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    sprite = _dashing_player()
    # The ghost pass walks entity_sprites: a dashing player is an entity, and
    # scanning all_sprites for it was the cost this change removed.
    groups.all_sprites.add(sprite)
    groups.entity_sprites.add(sprite)

    renderer.draw(groups, dt=Afterimage.SPAWN_EVERY)
    assert len(renderer._ghosts) == 1

    for _ in range(12):
        renderer.draw(groups, dt=Afterimage.SPAWN_EVERY)
    # Steady state: old ghosts expire as new ones spawn, never above the cap.
    assert 1 <= len(renderer._ghosts) <= Afterimage.MAX

    # Dash over: the whole trail fades out, nothing respawns.
    sprite.state_machine = SimpleNamespace(current_state_name="run")
    renderer.draw(groups, dt=Afterimage.TTL + 1.0)
    assert renderer._ghosts == []


def test_idle_player_spawns_no_ghosts() -> None:
    surface = pygame.Surface((64, 64))
    camera = Camera(Framing(float(64), float(64)))
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    sprite = DashSprite(state="run")
    groups.all_sprites.add(sprite)

    renderer.draw(groups, dt=1.0)

    assert renderer._ghosts == []


# --- Dust puffs -------------------------------------------------------------


def test_dust_puff_fades_and_reaps_itself() -> None:
    group = pygame.sprite.Group()
    puff = DustParticle((10.0, 10.0), (100.0, -50.0))
    group.add(puff)

    puff.update(Dust.TTL / 2.0)

    assert puff.alive()
    assert puff.rect.center != (10.0, 10.0)

    puff.update(Dust.TTL)

    assert not puff.alive()


def test_landing_fan_spawns_count_puffs_at_the_feet() -> None:
    entity = make_entity(pos=(100.0, 100.0))
    group = pygame.sprite.Group()

    puffs = spawn_landing_dust(group, entity)

    assert len(puffs) == Dust.COUNT
    assert len(group) == Dust.COUNT
    for puff in puffs:
        assert puff.ttl == pytest.approx(Dust.TTL)
        assert abs(puff.pos.x - entity.hitbox.centerx) < entity.hitbox.width


def test_dash_streak_lies_along_its_own_velocity() -> None:
    """A speed line has to point where it is going, or it is just a dash."""
    entity = make_entity(pos=(100.0, 100.0))
    entity.facing_right = True
    group = pygame.sprite.Group()

    streak = spawn_dash_streak(group, entity)

    assert streak is not None
    assert len(group) == 1
    assert streak.pos.x < entity.hitbox.centerx
    assert streak.velocity.x < 0.0
    assert streak.image.get_width() > streak.image.get_height() * 3


def test_dash_direction_prefers_live_velocity_over_facing() -> None:
    entity = make_entity(pos=(100.0, 100.0))
    entity.facing_right = True
    entity.velocity.x = -800.0

    assert dash_direction(entity) == pytest.approx(-1.0)

    puffs = spawn_dash_burst(pygame.sprite.Group(), entity)

    assert all(puff.pos.x > entity.hitbox.centerx for puff in puffs)
    assert all(puff.velocity.x > 0.0 for puff in puffs)

    entity.velocity.x = 0.0
    entity.facing_right = False
    assert dash_direction(entity) == pytest.approx(-1.0)


def test_dash_burst_kicks_a_fan_backward_on_start() -> None:
    entity = make_entity(pos=(100.0, 100.0))
    entity.facing_right = True
    group = pygame.sprite.Group()

    puffs = spawn_dash_burst(group, entity)

    assert len(puffs) == FxDash.BURST_COUNT
    assert len(group) == FxDash.BURST_COUNT
    for puff in puffs:
        assert puff.pos.x <= entity.hitbox.centerx
        assert puff.velocity.x < 0.0
    assert spawn_dash_burst(group, SimpleNamespace()) == []


def test_hard_landing_records_impact_while_hops_stay_clean() -> None:
    entity = make_entity(pos=(50.0, 155.0), faction="player")
    entity.collision_sprites = [_floor_tile()]
    entity.velocity.y = 600.0

    entity.update(1 / 60)

    assert entity.on_surface["floor"]
    assert entity.landed_impact == pytest.approx(600.0)
    assert entity.landed_impact >= Dust.MIN_FALL_SPEED

    entity.update(1 / 60)

    assert entity.landed_impact == pytest.approx(0.0)


def test_physics_spawns_landing_dust_and_dash_streaks() -> None:
    groups = SpriteGroups()
    lander = make_entity(pos=(50.0, 100.0))
    lander.landed_impact = Dust.MIN_FALL_SPEED + 100.0
    dasher = make_entity(pos=(200.0, 100.0))
    dasher.state_machine = SimpleNamespace(current_state_name="dash")
    groups.entity_sprites.add(lander, dasher)
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)

    # Landing fan plus its ground mark, then the one-shot dash-start burst,
    # the ground ring and the dash trail.
    assert len(groups.fx_sprites) == Dust.COUNT + 1 + FxDash.BURST_COUNT + 2 + FxDash.WIND_LINES


def test_dash_burst_fires_once_per_dash() -> None:
    groups = SpriteGroups()
    dasher = make_entity(pos=(200.0, 100.0))
    dasher.state_machine = SimpleNamespace(current_state_name="dash")
    groups.entity_sprites.add(dasher)
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)
    # Burst + ground ring + one trail particle + its wind lines on dash start.
    assert len(groups.fx_sprites) == FxDash.BURST_COUNT + 2 + FxDash.WIND_LINES

    # Still dashing: a speed line on top of the trail cadence.
    system._spawn_impact_fx(1 / 60)
    assert len(groups.fx_sprites) >= FxDash.BURST_COUNT + 2 + FxDash.WIND_LINES + 2

    # Dash over, then re-dash: the burst fires again. The first burst has to
    # be gone first, or the family cap refuses the second one and this would
    # be a test of the cap wearing this test's name.
    dasher.state_machine = SimpleNamespace(current_state_name="run")
    system._spawn_impact_fx(1 / 60)
    for _ in range(30):
        for sprite in list(groups.fx_sprites):
            sprite.update(1 / 60)
    assert len(groups.fx_sprites) == 0, "the first dash's fx have reaped themselves"

    dasher.state_machine = SimpleNamespace(current_state_name="dash")
    system._spawn_impact_fx(1 / 60)
    assert len(groups.fx_sprites) == FxDash.BURST_COUNT + 2 + FxDash.WIND_LINES


def test_fx_spawning_stops_past_the_particle_budget() -> None:
    groups = SpriteGroups()
    dasher = make_entity(pos=(200.0, 100.0))
    dasher.state_machine = SimpleNamespace(current_state_name="dash")
    dasher.landed_impact = Dust.MIN_FALL_SPEED + 100.0
    groups.entity_sprites.add(dasher)
    for _ in range(MAX_FX_SPRITES):
        groups.fx_sprites.add(DustParticle((0.0, 0.0), (0.0, 0.0)))
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)

    assert len(groups.fx_sprites) == MAX_FX_SPRITES
    # The landing hint is still consumed: no debt for later ticks.
    assert dasher.landed_impact == pytest.approx(0.0)


def test_afterimage_ghosts_carry_the_speed_tint() -> None:
    surface = pygame.Surface((64, 64))
    # zoom=1.0: this test asserts world-sized ghost geometry.
    camera = Camera(Framing(float(64), float(64)))
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    dasher = _dashing_player()
    groups.all_sprites.add(dasher)
    groups.entity_sprites.add(dasher)

    renderer.draw(groups, dt=Afterimage.SPAWN_EVERY)

    ghost = renderer._ghosts[0][0]
    # Tinted white, and stretched wide-and-low like the live dash frame.
    assert ghost.get_at((0, 0)) == pygame.Color(170, 220, 255, 255)
    assert ghost.get_width() == int(20 * DASH_STRETCH_X)
    assert ghost.get_height() == int(30 * DASH_STRETCH_Y)


def test_dash_frame_stretches_and_recenters() -> None:
    image = pygame.Surface((20, 30))
    screen_rect = pygame.Rect(10, 10, 20, 30)

    stretched, rect = dash_frame(image, screen_rect)

    assert stretched.get_width() == int(20 * DASH_STRETCH_X)
    assert stretched.get_height() == int(30 * DASH_STRETCH_Y)
    assert rect.center == screen_rect.center


def test_is_player_dashing_only_matches_dashing_players() -> None:
    assert is_player_dashing(_dashing_player())
    idle = DashSprite(state="run")
    assert not is_player_dashing(idle)
    enemy = DashSprite(state="dash")
    enemy.faction = "enemy"
    assert not is_player_dashing(enemy)
    assert not is_player_dashing(SimpleNamespace())


def test_dash_cycles_the_run_animation_instead_of_freezing() -> None:
    from src.core.input.input_manager import InputManager  # noqa: PLC015
    from src.entities.player import Player  # noqa: PLC015

    player = Player(
        pos=(0, 0),
        groups=pygame.sprite.Group(),
        collision_sprites=pygame.sprite.Group(),
        moving_platforms=[],
        input_manager=InputManager(),
    )
    player.state_machine.current_state_name = "dash"

    # Now has dedicated dash animation (falls back to run if not available)
    assert player._animation_name() == "dash"


def test_dash_trail_spawns_fast_thin_streaks() -> None:
    entity = make_entity(pos=(100.0, 100.0))
    entity.velocity.x = 1500.0
    group = pygame.sprite.Group()

    streak = spawn_dash_streak(group, entity)

    assert isinstance(streak, StreakParticle)
    assert streak.image.get_width() > streak.image.get_height() * 3
    assert streak.velocity.x < 0.0
    assert streak.pos.x <= entity.hitbox.centerx
    assert spawn_dash_streak(group, SimpleNamespace()) is None


def test_streak_slides_back_and_reaps_itself() -> None:
    group = pygame.sprite.Group()
    streak = StreakParticle((50.0, 50.0), (-600.0, 0.0), length=24.0)
    group.add(streak)
    start_x = streak.pos.x

    streak.update(0.1)

    assert streak.alive()
    assert streak.pos.x < start_x
    streak.update(1.0)
    assert not streak.alive()


def test_framed_puffs_shrink_cycle_and_fall_back_to_circles() -> None:
    group = pygame.sprite.Group()
    frames = [pygame.Surface((10, 10)), pygame.Surface((8, 8)), pygame.Surface((6, 6))]
    puff = DustParticle((10.0, 10.0), (0.0, 0.0), ttl=0.3, frames=frames)
    group.add(puff)
    first_size = puff.image.get_size()

    puff.update(0.2)

    assert puff.alive()
    assert puff.image.get_size() != first_size

    plain = DustParticle((10.0, 10.0), (0.0, 0.0), radius=5.0)
    assert plain.image.get_size() == (10, 10)
    assert plain.frames is None


def test_light_impacts_spawn_no_dust() -> None:
    assert list(iter_landing_entities([SimpleNamespace(landed_impact=100.0)])) == []
    entity = SimpleNamespace(landed_impact=Dust.MIN_FALL_SPEED)
    assert list(iter_landing_entities([entity])) == [(entity, Dust.MIN_FALL_SPEED)]


# --- Dash-penalty sweat ---------------------------------------------------


class DashStateStub:
    """Minimal dash-controller stand-in for sweat gating."""

    def __init__(self, charges: int = 0, penalty_timer: float = 1.0) -> None:
        self.charges = charges
        self.penalty_timer = penalty_timer


_NO_DASH = object()


class PenaltySprite(pygame.sprite.Sprite):
    """Minimal player-like sprite with a switchable dash resource."""

    def __init__(
        self,
        dash: DashStateStub | None | object = _NO_DASH,
    ) -> None:
        super().__init__()
        self.hitbox = pygame.FRect(100.0, 100.0, 24.0, 40.0)
        self.on_surface = {"floor": False}
        # ``_NO_DASH`` defaults to a drained controller; ``None`` drops the
        # dash resource entirely (enemies never sweat).
        if dash is _NO_DASH:
            dash = DashStateStub()
        self.dash = dash


def test_sweat_drops_bead_beside_the_head_and_fall() -> None:
    """They bead off the temple the dasher is facing, not off the middle.

    A drop that comes out of the centre of the crown lands on top of the
    hair and reads as a hat; one that comes out beside it reads as sweat.
    """
    entity = make_entity(pos=(100.0, 100.0))
    entity.facing_right = True
    entity.rng = random.Random(7)
    group = pygame.sprite.Group()

    drops = spawn_sweat_drops(group, entity)

    assert len(drops) == Sweat.COUNT
    assert all(isinstance(drop, SweatParticle) for drop in drops)
    for drop in drops:
        assert drop.rect.centery <= entity.hitbox.top + 12.0
        assert drop.velocity.y < 0.0
        assert drop.pos.x > entity.hitbox.centerx
        assert drop.pos.x <= entity.hitbox.right
    # Heavier than dust: gravity turns the pop into a fall.
    drops[0].update(0.2)
    assert drops[0].velocity.y > 0.0
    falling_from = drops[0].pos.y
    drops[0].update(0.2)
    assert drops[0].pos.y > falling_from


def test_sweat_beads_read_as_thick_comic_teardrops() -> None:
    drop = SweatParticle((50.0, 50.0), (0.0, -10.0))
    image = drop.image
    width, height = image.get_size()

    # A teardrop, not a dot: the tapered tip makes it taller than wide.
    assert height > width
    # Fat bead: the whole inked sprite is several pixels across.
    assert width >= 3 * SweatSettings.OUTLINE_WIDTH
    # Comic palette: pale fill, bold ink outline, glossy white glint.
    colors = {tuple(image.get_at((x, y)))[:3] for x in range(width) for y in range(height)}
    assert tuple(FXColors.sweat)[:3] in colors
    assert tuple(FXColors.sweat_ink)[:3] in colors
    assert tuple(FXColors.sweat_shine)[:3] in colors
    # Ink rim under the fill: scanning the center column, the bulb bottoms
    # out on a bold outline row with pale fill sitting just above it.
    column = [tuple(image.get_at((width // 2, y))) for y in range(height)]
    opaque_rows = [y for y, pixel in enumerate(column) if pixel[:3] != (0, 0, 0)]
    assert column[max(opaque_rows)][:3] == tuple(FXColors.sweat_ink)[:3]
    assert column[max(opaque_rows) - 2][:3] == tuple(FXColors.sweat)[:3]


def test_sweat_droplet_arcs_then_reaps_itself() -> None:
    group = pygame.sprite.Group()
    drop = SweatParticle((50.0, 50.0), (20.0, -60.0))
    group.add(drop)

    drop.update(0.2)
    assert drop.alive()
    assert drop.pos.y > 50.0 - 60.0 * 0.2  # gravity ate part of the pop
    drop.update(Sweat.TTL)
    assert not drop.alive()


def test_sweat_needs_a_hitbox_to_bead_from() -> None:
    group = pygame.sprite.Group()

    assert spawn_sweat_drops(group, SimpleNamespace()) == []
    assert list(group) == []


def test_penalty_dashers_sweat_on_a_cadence() -> None:
    entity = PenaltySprite()
    groups = SimpleNamespace(
        entity_sprites=pygame.sprite.Group(entity),
        moving_platforms=[],
        fx_sprites=pygame.sprite.Group(),
    )
    system = PhysicsSystem(groups)

    system.process(1 / 60)  # penalty begins: the first drop fires immediately
    first_drop = system.groups.fx_sprites.sprites()[0]
    assert isinstance(first_drop, SweatParticle)

    system.process(1 / 60)  # cadence holds: no extra drop until SPAWN_EVERY
    assert len(system.groups.fx_sprites) == 1

    system.process(Sweat.SPAWN_EVERY)
    assert len(system.groups.fx_sprites) == 2


def test_dash_pools_stop_sweating_when_penalty_ends() -> None:
    entity = PenaltySprite(dash=DashStateStub(charges=2, penalty_timer=0.0))
    groups = SimpleNamespace(
        entity_sprites=pygame.sprite.Group(entity),
        moving_platforms=[],
        fx_sprites=pygame.sprite.Group(),
    )
    system = PhysicsSystem(groups)

    system.process(1 / 60)

    assert len(groups.fx_sprites) == 0


def test_sweat_stops_when_the_dasher_leaves_the_level() -> None:
    entity = PenaltySprite()
    groups = SimpleNamespace(
        entity_sprites=pygame.sprite.Group(entity),
        moving_platforms=[],
        fx_sprites=pygame.sprite.Group(),
    )
    system = PhysicsSystem(groups)
    system.process(1 / 60)

    entity.kill()  # groups.entity_sprites is now empty
    system.process(Sweat.SPAWN_EVERY * 2)

    # The stale per-entity timer was pruned with its entity.
    assert system._sweat_timers == {}


def test_dash_only_entities_never_sweat() -> None:
    entity = PenaltySprite(dash=None)
    groups = SimpleNamespace(
        entity_sprites=pygame.sprite.Group(entity),
        moving_platforms=[],
        fx_sprites=pygame.sprite.Group(),
    )
    system = PhysicsSystem(groups)

    system.process(1 / 60)

    assert len(groups.fx_sprites) == 0


def test_every_spawner_declines_an_entity_that_has_no_body() -> None:
    """FX takes any duck-typed entity, including one mid-removal.

    The spawners read `entity.hitbox` and hand back nothing when it is
    absent, rather than raising. A projectile, or a fighter being pulled out
    of the group by a loop that is still holding a reference, is exactly the
    kind of thing that reaches a spawner -- and a `None` return is the one
    answer that cannot leave a half-added particle behind.
    """
    group = pygame.sprite.Group()
    bare = SimpleNamespace()

    assert spawn_landing_dust(group, bare) == []
    assert spawn_impact_decal(group, bare) is None
    assert spawn_dash_burst(group, bare) == []
    assert spawn_dash_streak(group, bare) is None
    assert spawn_dash_wind(group, bare) == []
    assert spawn_dash_shockwave(group, bare) is None
    assert spawn_dash_trail(group, bare) is None
    assert spawn_dizzy_stars(group, bare) == []
    assert spawn_dizzy_vortex(group, bare) is None
    assert spawn_sweat_drops(group, bare) == []
    assert spawn_guard_arc(group, bare) is None
    assert spawn_shatter_arc(group, bare) is None
    assert len(group) == 0, "and nothing was added on the way past"


def test_a_spawner_whose_family_is_full_declines_rather_than_waiting() -> None:
    """The cap is per family, so a full star budget must not touch the swirl.

    Stars and the swirl are separate families because they are separate
    effects. Spending one budget must not silence the other, which is the
    whole reason the table is keyed per family rather than counted in one
    pile.

    It also pins the budget as a ceiling rather than a threshold: a call that
    would take the family past its number is refused whole, so the six stars
    a spawner adds at a time cannot land on top of a nearly-full budget. That
    check once read "is there room for one", which let `dizzy_star` reach 12
    against a budget of 8.
    """
    group = pygame.sprite.Group()
    box = pygame.FRect(100, 100, 40, 48)
    entity = SimpleNamespace(hitbox=box, velocity=pygame.math.Vector2(0.0, 0.0))

    while spawn_dizzy_stars(group, entity):
        pass
    stars = len(group)
    assert stars <= FX_FAMILY_BUDGETS["dizzy_star"], "and never a particle past it"

    assert spawn_dizzy_stars(group, entity) == [], "the star budget is spent"
    assert spawn_dizzy_vortex(group, entity) is not None, "but the swirl has its own"
    assert len(group) == stars + 1, "only the swirl was added"

    # The other two cadenced effects refuse the same way, one particle at a
    # time, so the check is not special to a batch.
    swirl = pygame.sprite.Group()
    while spawn_dizzy_vortex(swirl, entity) is not None:
        pass
    assert len(swirl) == FX_FAMILY_BUDGETS["dizzy_vortex"]
    assert spawn_dizzy_vortex(swirl, entity) is None, "a full swirl budget refuses too"

    drops = pygame.sprite.Group()
    while spawn_sweat_drops(drops, entity):
        pass
    assert len(drops) == FX_FAMILY_BUDGETS["sweat"]
    assert spawn_sweat_drops(drops, entity) == [], "and so does a full sweat budget"


def test_a_family_the_budget_table_has_never_heard_of_is_still_allowed() -> None:
    """An unknown family is not blocked -- the invariant is what catches it.

    Refusing here would mean a typo in a spawner's family name silently turns
    its effect off, in the release build, with the cap as the reason. The
    budget table is checked against the source by `test_fx_invariants`
    instead, which fails in CI rather than in front of a player.
    """
    assert spawners._has_room(pygame.sprite.Group()) is True, "no family named, nothing to check"
    assert spawners._has_room(pygame.sprite.Group(), "a_family_nobody_declared") is True
    assert spawners._has_room(pygame.sprite.Group(), "dizzy_star") is True
