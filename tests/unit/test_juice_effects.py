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
    SweatParticle,
    iter_landing_entities,
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
from src.core.rendering.renderer import _ghost_alpha as renderer_alpha
from src.core.settings import Afterimage, Dust, HitFlash, Physics, Simulation, Sweat
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


def _detailed_dasher() -> DashSprite:
    """A dashing sprite with real tones and an alpha channel.

    `DashSprite` is a flat white rectangle, which is fine for asserting a
    ghost's size and useless for asserting anything about its colours: any
    implementation -- a tint, a flat fill, a greyscale -- lands on the same
    value for a one-colour source, so the assertion passes for the wrong
    reason. This one has a dark outline, two body tones and a transparent
    corner, so "monochrome" and "not a flat fill" are distinguishable.
    """
    dasher = DashSprite(state="dash")
    dasher.image = pygame.Surface((20, 30), pygame.SRCALPHA)
    dasher.image.fill((200, 60, 40, 255))
    dasher.image.fill((120, 190, 120, 255), (4, 4, 12, 22))
    dasher.image.set_at((0, 0), (30, 30, 90, 255))
    dasher.image.set_at((19, 0), (0, 0, 0, 0))
    dasher.rect = pygame.FRect(10, 10, 20, 30)
    return dasher


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
        assert puff.ttl <= Dust.TTL + 1e-9
        assert puff.ttl >= Dust.TTL * Dust.TTL_JITTER[0] - 1e-9
        assert abs(puff.pos.x - entity.hitbox.centerx) < entity.hitbox.width


def test_the_fan_dissolves_instead_of_vanishing_on_one_frame() -> None:
    """Six puffs sharing one TTL blinked out together, which read as a cut.

    The lives are staggered by how far each puff was thrown, so the fan
    dissolves from the middle out and the outer puffs -- the ones that carry
    the landing -- are the last to go.
    """
    entity = make_entity(pos=(100.0, 100.0))

    puffs = spawn_landing_dust(pygame.sprite.Group(), entity)

    lives = [puff.ttl for puff in puffs]
    assert len(set(lives)) > 1, f"the fan has to stagger: {lives}"
    assert lives[0] > lives[len(lives) // 2], "and the outer puffs live longer"
    assert max(lives) - min(lives) > 0.0


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


def test_a_hard_landing_spawns_its_fan_and_its_ground_mark() -> None:
    groups = SpriteGroups()
    lander = make_entity(pos=(50.0, 100.0))
    lander.landed_impact = Dust.MIN_FALL_SPEED + 100.0
    groups.entity_sprites.add(lander)
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)

    assert len(groups.fx_sprites) == Dust.COUNT + 1


def test_a_dash_spawns_no_particles_at_all() -> None:
    """The dash's whole visual is the renderer's afterimage, and nothing else.

    It used to be five systems on one 80ms event: a backward fan of dust, a
    ground ring, a speed line every tick, wind lines on a cadence, and a
    comet. Four of them marked the path the afterimage already photographs,
    and the frame they produced was a white cloud under a stretched
    rectangle with a hoop around it.

    So a dashing entity now spends no particle budget at all, and this holds
    it there. Adding a mark back is a deliberate act against this test, not
    an accident of a spawner that forgot to ask.
    """
    groups = SpriteGroups()
    dasher = make_entity(pos=(200.0, 100.0))
    dasher.state_machine = SimpleNamespace(current_state_name="dash")
    groups.entity_sprites.add(dasher)
    system = PhysicsSystem(groups)

    for _ in range(6):
        system._spawn_impact_fx(1 / 60)

    assert len(groups.fx_sprites) == 0


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
    # A flat white source, so the greyscale leaves it white and the tint
    # decides the value. The multi-tone case is the other test; this one is
    # here because it is the arithmetic of the multiply.
    assert ghost.get_at((0, 0)) == pygame.Color(*FXColors.speed_ghost, 255)


def test_an_afterimage_keeps_the_fighter_s_shape_and_not_the_dash_stretch() -> None:
    """The stretch is a cue for the movement; a frozen copy of it is a lozenge.

    The ghosts used to be built through `dash_frame`, so every stamp was the
    sprite at 1.6 wide and 0.6 tall. The live sprite is only ever seen
    stretched for the few frames it is moving, and the eye reads that as
    speed. Frozen, the same shape is three pancakes in a row, and it is not
    the fighter any more.

    So the afterimage is the sprite at its own proportions, and this fails if
    the stretch is put back into the spawn.
    """
    surface = pygame.Surface((64, 64))
    camera = Camera(Framing(float(64), float(64)))
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    dasher = _dashing_player()
    groups.all_sprites.add(dasher)
    groups.entity_sprites.add(dasher)

    renderer.draw(groups, dt=Afterimage.SPAWN_EVERY)

    ghost = renderer._ghosts[0][0]
    assert (ghost.get_width(), ghost.get_height()) == (20, 30), "the fighter's own shape"
    assert ghost.get_height() == 30, "not the dash frame's half height"
    assert ghost.get_width() != int(20 * DASH_STRETCH_X), "nor the dash frame's width"


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


def test_a_puff_billows_through_its_ladder_and_snaps_its_radius() -> None:
    """A puff opens as it dies, and its size is one a ladder already holds.

    The old version of this test pinned the shipped debris frames: three
    fixed 30px PNGs, scaled by a constant, cycled per tick. It failed for a
    reason the test never noticed -- ``radius`` was ignored entirely on that
    path, so a puff asked for at 5px and one asked for at 11px came out the
    same size on screen, and "a hard landing throws heavier puffs" was true
    of the velocity and nothing else.
    """
    group = pygame.sprite.Group()
    puff = DustParticle((10.0, 10.0), (0.0, 0.0), ttl=0.3)
    group.add(puff)
    widths = [puff.image.get_width()]

    for _ in range(2):
        puff.update(0.1)
        widths.append(puff.image.get_width())

    assert puff.alive()
    assert widths == sorted(widths), f"the puff has to open, not close: {widths}"

    small = DustParticle((10.0, 10.0), (0.0, 0.0), radius=3.0)
    large = DustParticle((10.0, 10.0), (0.0, 0.0), radius=13.0)
    assert small.ladder[-1].get_width() < large.ladder[-1].get_width()


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


def test_the_afterimages_step_down_in_plates_rather_than_fading() -> None:
    """A manga afterimage is a flat stamp, not a ramp, and this holds it there.

    The trail used to be fourteen copies at a continuous alpha over a third of
    a second, which is motion blur. A manga speed line is a few solid
    silhouettes that stop. So the opacity walks a fixed ladder, each level
    holding an equal share of the ghost's life, and the test fails if
    anything puts a slope back between them.
    """
    levels = Afterimage.LEVELS
    assert len(levels) >= 2, "a single level would be no fade at all"
    assert levels == tuple(sorted(levels, reverse=True)), "brightest first"
    assert all(level > 0 for level in levels)

    seen = {renderer_alpha(ttl) for ttl in (0.99, 0.9, 0.7, 0.6, 0.4, 0.3, 0.1, 0.0)}
    assert seen <= set(levels), f"an opacity outside the ladder: {sorted(seen - set(levels))}"
    assert len(seen) == len(levels), "every level is reached as a ghost ages"

    # A ramp would produce a different opacity at nearly every age instead.
    ramp = {int(255 * ttl / Afterimage.TTL) for ttl in (0.99, 0.9, 0.7, 0.6, 0.4, 0.3, 0.1)}
    assert len(ramp) == 7, "which is what the old fade produced"


def test_the_afterimage_count_is_bounded_by_one_dash_not_by_taste() -> None:
    """The cap exists so a trail cannot stack across dashes, not to keep it short.

    How many stamps look right is a matter of taste and has moved twice. Two
    things are not: the cap must be able to hold every stamp a single dash
    lays down, or the trail is truncated mid-dash and the dash looks broken;
    and one dash's trail must be gone before the next dash can start, or the
    copies of two dashes pile up in the same place.
    """
    # Bounded by the cadence and by the frame: a stamp cannot land twice in
    # one tick, so a cadence finer than a frame is really a per-frame rate.
    frame = 1.0 / Simulation.TICK_RATE
    per_dash = min(Physics.DASH_DURATION / Afterimage.SPAWN_EVERY, Physics.DASH_DURATION / frame)
    assert per_dash <= Afterimage.MAX, (
        f"an {Physics.DASH_DURATION * 1000:.0f}ms dash lays {per_dash:.1f} stamps, "
        f"and the cap is {Afterimage.MAX}"
    )
    assert Afterimage.TTL < Physics.DASH_RECHARGE_TIME, "gone before the next dash"


def test_the_afterimages_are_monochrome_copies_and_not_flat_fills() -> None:
    """Hue out, shading in, outline in, transparency kept.

    "Noir et blanc" was implemented once as a flat near-black fill, and that
    was wrong: it threw away the shading and the outline as well as the hue,
    so five of them in a row were five blobs. This is the assertion that
    would have caught it -- a flat fill is one colour, and this sprite is
    not.

    A dashed ghost also has to stay greyscale. Tinting it would put the hue
    straight back, and the hue is the only thing that was meant to go.
    """
    surface = pygame.Surface((64, 64))
    camera = Camera(Framing(float(64), float(64)))
    camera.set_world_size(64, 64)
    renderer = Renderer(surface, camera)
    groups = SpriteGroups()
    dasher = _detailed_dasher()
    groups.all_sprites.add(dasher)
    groups.entity_sprites.add(dasher)

    renderer.draw(groups, dt=Afterimage.SPAWN_EVERY)

    ghost, _, _ = renderer._ghosts[0]
    assert ghost.get_size() == dasher.image.get_size(), "the same shape, not the dash stretch"

    hues: set[tuple[float, float]] = set()
    tones: set[int] = set()
    for y in range(ghost.get_height()):
        for x in range(ghost.get_width()):
            pixel = ghost.get_at((x, y))
            source = dasher.image.get_at((x, y))
            if source[3] == 0:
                assert pixel[3] == 0, f"({x},{y}) opaque where the sprite is not"
                continue
            assert pixel[3] == 255, f"({x},{y}) partly transparent inside the sprite"
            red, green, blue = pixel[:3]
            # Monochrome means one hue, not three equal channels: the tint is
            # multiplied over a greyscale, so the channels differ by a fixed
            # ratio. Normalising by the brightest channel is what makes that
            # checkable -- every pixel has to land on the same chromaticity.
            peak = max(red, green, blue)
            assert peak > 0, f"({x},{y}) is black"
            hues.add((round(red / peak, 2), round(green / peak, 2)))
            tones.add(peak)

    # A tolerance, not equality: an eight-bit ramp in the dark end quantises
    # unevenly, so two greys 38 and 40 apart in peak land on slightly
    # different chromaticities. One hue means within a rounding of each other.
    spread = max(abs(a - b) for a, b in zip(*sorted(hues), strict=True)) if hues else 1.0
    assert spread <= 0.05, f"more than one hue across the ghost: {sorted(hues)}"
    assert len(tones) >= 3, f"a flat fill would be one tone, got {len(tones)}: the shading is gone"
