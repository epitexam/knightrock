"""Game-feel juice: hit flash, dash afterimages, sweat drops, dust puffs."""

import os
import random
import statistics
from collections.abc import Iterator
from types import SimpleNamespace

import pygame
import pytest

from src.core.colors import FXColors
from src.core.display.framing import Framing
from src.core.fx import (
    FX_FAMILY_BUDGETS,
    MAX_FX_SPRITES,
    DashDustParticle,
    DustParticle,
    FootstepDustParticle,
    SweatParticle,
    iter_landing_entities,
    spawn_dizzy_stars,
    spawn_dizzy_vortex,
    spawn_footstep_dust,
    spawn_guard_arc,
    spawn_impact_decal,
    spawn_landing_dust,
    spawn_shatter_arc,
    spawn_sweat_drops,
    spawners,
)
from src.core.level.systems import physics_system
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
from src.core.settings import (
    Afterimage,
    DashDust,
    Dust,
    DustGrain,
    FootstepDust,
    HitFlash,
    Locomotion,
    Physics,
    Simulation,
    Sweat,
)
from src.core.settings import Guard as GuardSettings
from src.core.settings import Sweat as SweatSettings
from src.core.sprite_groups import SpriteGroups
from src.states.player_states import PlayerState
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

    assert len(_by_family(groups, "landing_dust")) == Dust.COUNT
    assert len(_by_family(groups, "dust_grain")) == DustGrain.LANDING_COUNT
    assert len(_by_family(groups, "impact_decal")) == 1


def _by_family(groups: SpriteGroups, family: str) -> list[object]:
    """The sprites in the FX plane that spend from ``family``.

    Written as a filter rather than a count because the dust now arrives in two
    families at once: a landing is sheets *and* a spray of grains, and half a
    dozen of these tests are about one of them. Counting the whole plane would
    make every one of them a test of the other.
    """
    return [sprite for sprite in groups.fx_sprites if sprite.family == family]


def _dasher(grounded: bool = True) -> object:
    """A fighter mid-dash, standing on a floor unless asked otherwise.

    Ground is not a detail here: the trail is emitted only over a floor, and
    a bare ``Entity`` is airborne by default, so a dash test that forgets to
    ask for ground would be testing that a dash draws nothing.
    """
    entity = make_entity(pos=(200.0, 100.0))
    entity.state_machine = SimpleNamespace(current_state_name="dash")
    entity.on_surface["floor"] = grounded
    return entity


def test_a_dash_trails_dust_and_nothing_else() -> None:
    """The dash carries one mark, and this holds it to one.

    It used to be five systems on one 80ms event: a backward fan of dust, a
    ground ring, a speed line every tick, wind lines on a cadence, and a
    comet. Four of them marked the path the afterimage already photographs,
    and the frame they produced was a white cloud under a stretched rectangle
    with a hoop around it.

    So the strip-out left the dash with no particles at all, which was its own
    kind of wrong: nothing in the plane said the fighter had displaced
    anything. A trail is the one mark that says it, and it is the only one
    allowed back -- a second is a step along the road to the white cloud.

    The count is therefore a burst plus one cadence emission per tick, and
    the ticks are fewer than the burst: the ribbon is not allowed to weigh as
    much as the shove that started it.
    """
    groups = SpriteGroups()
    groups.entity_sprites.add(_dasher())
    system = PhysicsSystem(groups)

    ticks = int(Physics.DASH_DURATION * 60)
    for _ in range(ticks):
        system._spawn_impact_fx(1 / 60)

    trail = _by_family(groups, "dash_dust")
    assert trail, "a dash leaves a trail"
    assert all(sprite.family in ("dash_dust", "dust_grain") for sprite in groups.fx_sprites), (
        f"and nothing else: {[s.family for s in groups.fx_sprites]}"
    )
    assert len(trail) > DashDust.BURST_COUNT, "the ribbon extends past the shove"
    assert len(trail) <= DashDust.BURST_COUNT + ticks * DashDust.TICK_COUNT, (
        f"and it is a ribbon, not a wall: {len(trail)} puffs over {ticks} ticks"
    )
    assert _by_family(groups, "dust_grain"), "and the trail carries grit as well as mass"


def test_the_dash_trail_bursts_once_per_dash_and_not_once_per_tick() -> None:
    """The burst is a shove, and a shove repeated is a stutter.

    Without a way to tell one dash from the next, the burst would fire on
    every tick of the dash and the trail would open with a pile of clouds
    rather than a shove followed by a ribbon.
    """
    groups = SpriteGroups()
    groups.entity_sprites.add(_dasher())
    system = PhysicsSystem(groups)

    for _ in range(3):
        system._spawn_impact_fx(1 / 60)

    radii = [sprite.radius for sprite in _by_family(groups, "dash_dust")]
    assert radii.count(max(radii)) == 1, f"exactly one puff at the burst's size: {radii}"


def test_a_second_dash_bursts_again() -> None:
    """Coming out of the dash has to re-arm it, or a second dash has no shove.

    The trail reads the entity leaving the dash state as the end of one, which
    is what clears the timer. A fighter with five charges can dash five times
    in a second, and each one is a separate movement that deserves its own
    impact.
    """
    groups = SpriteGroups()
    dasher = _dasher()
    groups.entity_sprites.add(dasher)
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)
    first = len(_by_family(groups, "dash_dust"))
    dasher.state_machine = SimpleNamespace(current_state_name="idle")
    system._spawn_impact_fx(1 / 60)
    assert len(_by_family(groups, "dash_dust")) == first, "an idle entity trails nothing"
    dasher.state_machine = SimpleNamespace(current_state_name="dash")
    system._spawn_impact_fx(1 / 60)

    assert len(_by_family(groups, "dash_dust")) == first + DashDust.BURST_COUNT


def test_the_dash_trail_stops_at_the_family_budget() -> None:
    """The trail cannot spend the plane, or a dash starves a parry.

    It is refused whole rather than half-landed: a ribbon that stops halfway
    reads as the dash running out of dust, which is not a thing.
    """
    groups = SpriteGroups()
    groups.entity_sprites.add(_dasher())
    cap = FX_FAMILY_BUDGETS["dash_dust"]
    for _ in range(cap - 1):
        groups.fx_sprites.add(DashDustParticle((0.0, 0.0), (0.0, 0.0)))
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)

    assert len(_by_family(groups, "dash_dust")) == cap - 1, (
        "a burst that does not fit is not half-thrown"
    )


def test_a_dash_in_mid_air_trails_nothing() -> None:
    """Dust needs a floor to come off, and there is a very common dash without one.

    The dash is available in the air, so this is the majority of the dashes
    a player makes in a platformer and it was the first thing that looked
    wrong. A plume hanging at the height of a jump reads as the fighter
    smearing the screen, not as ground he pushed away -- and it is drawn
    behind him, so it sits against the sky where nothing else in the plane
    does, at the exact moment the eye is busiest.

    Nothing replaces it. A dash in the air displaces nothing there is dust
    of, and the effect is only worth having because it means a floor.
    """
    groups = SpriteGroups()
    groups.entity_sprites.add(_dasher(grounded=False))
    system = PhysicsSystem(groups)

    for _ in range(int(Physics.DASH_DURATION * 60)):
        system._spawn_impact_fx(1 / 60)

    assert len(groups.fx_sprites) == 0


def test_a_dash_that_leaves_the_ground_stops_trail_but_keeps_its_dust() -> None:
    """A dash that runs off a ledge thins out, it does not vanish.

    What is already in the world is a mark the player has already been
    shown, and yanking it is worse than the air trail was. So the emission
    stops and the puffs carry on evaporating where they were laid.
    """
    groups = SpriteGroups()
    dasher = _dasher()
    groups.entity_sprites.add(dasher)
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)
    laid = len(groups.fx_sprites)
    assert laid

    dasher.on_surface["floor"] = False
    for _ in range(int(Physics.DASH_DURATION * 60)):
        system._spawn_impact_fx(1 / 60)

    assert len(groups.fx_sprites) == laid, "no more puffs once there is no floor"


def test_a_dash_that_begins_airborne_spends_its_burst_on_landing() -> None:
    """The shove belongs to the start of the dash, and this one did not have a floor.

    So it is spent without being thrown, and the landing that follows brings
    its own dust from the fall speed the landing fan already reads. The
    alternative -- holding the burst until the fighter happens to be over a
    floor -- puts a second plume on a landing that already has a fan and a
    ground mark, and puts it there a moment late.
    """
    groups = SpriteGroups()
    dasher = _dasher(grounded=False)
    groups.entity_sprites.add(dasher)
    system = PhysicsSystem(groups)

    for _ in range(int(Physics.DASH_DURATION * 60)):
        system._spawn_impact_fx(1 / 60)
    assert len(groups.fx_sprites) == 0

    dasher.on_surface["floor"] = True
    for _ in range(int(Physics.DASH_DURATION * 60)):
        system._spawn_impact_fx(1 / 60)

    radii = [sprite.radius for sprite in _by_family(groups, "dash_dust")]
    assert max(radii) < DashDust.BURST_RADIUS, "and the burst was not held back for it"


def test_a_landing_still_wins_the_plane_over_a_dash_trail() -> None:
    """A hard landing is the harder event, and the trail yields to it.

    The trail is a cadenced effect and the landing is not, so the budget
    table is sized to let the one-shot through first. Both fire on the same
    tick when a fighter lands out of a dash, and the landing is the one the
    player is reading.
    """
    groups = SpriteGroups()
    dasher = _dasher()
    dasher.landed_impact = Dust.MIN_FALL_SPEED + 100.0
    groups.entity_sprites.add(dasher)
    for _ in range(FX_FAMILY_BUDGETS["dash_dust"]):
        groups.fx_sprites.add(DashDustParticle((0.0, 0.0), (0.0, 0.0)))
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)

    families = [sprite.family for sprite in groups.fx_sprites]
    assert families.count("landing_dust") == Dust.COUNT, "the landing is not refused"
    assert families.count("dash_dust") == FX_FAMILY_BUDGETS["dash_dust"], (
        "and the trail is what gets refused"
    )


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


# --- Footsteps -------------------------------------------------------------


class _StepSpy:
    """Counts the footsteps a run of ticks asked for, and which foot threw them.

    Counting the spawns rather than the sprites is the point. ``COUNT`` puffs
    per step evaporate in ``FootstepDust.TTL``, so a count of what is *alive*
    is a function of the last three tenths of a second and would quietly cap
    itself at whatever survived, which is a number that happens to be near the
    right one and is not the thing under test.
    """

    def __init__(self) -> None:
        self.feet: list[bool] = []
        self.tiers: list[object] = []

    def __call__(
        self,
        fx_group: pygame.sprite.Group,
        entity: object,
        foot: bool = False,
        tier: object = None,
    ) -> None:
        self.feet.append(foot)
        self.tiers.append(tier)


@pytest.fixture
def _spy_on_steps(monkeypatch: pytest.MonkeyPatch) -> _StepSpy:
    """Replace the emitter with a counter, and leave the plane untouched.

    The spawner is patched rather than wrapped so a refused step is counted too:
    a test that only counts the puffs that made it into the plane cannot tell a
    cadence from a budget.
    """
    spy = _StepSpy()
    monkeypatch.setattr(physics_system, "spawn_footstep_dust", spy)
    return spy


def _walker(
    speed: float = Physics.PLAYER_SPEED,
    grounded: bool = True,
    state: str = "run",
) -> object:
    """A fighter rolling along a floor, in the ground tier called ``state``.

    Moved by hand between ticks rather than integrated: this section is about
    the cadence the emitter reads, and giving the real movement in would put
    ``PlayerGroundLocomotionState`` and friction between the test and the thing
    it is measuring. The emitter only ever reads ``velocity.x`` and the state
    name, so moving the rect to match is enough to keep the two consistent.

    ``state`` is a ``PlayerState`` value and it is not decoration: the footstep
    table is keyed on it, so a test that leaves it at ``run`` while walking at
    a quarter speed is measuring a run's cadence at a walk's pace.
    """
    entity = make_entity(pos=(200.0, 100.0))
    entity.speed = Physics.PLAYER_SPEED
    entity.velocity.x = speed
    entity.on_surface["floor"] = grounded
    entity.state_machine = SimpleNamespace(current_state_name=state)
    return entity


def _walk(system: PhysicsSystem, entity: object, speed: float, ticks: int) -> None:
    for _ in range(ticks):
        entity.rect.x += speed / 60.0
        system._spawn_impact_fx(1 / 60)


def test_a_fighter_rolling_on_a_floor_leaves_footsteps() -> None:
    """The mark that says the fighter is moving at all.

    Landing dust answers "how hard was that" and the dash trail answers "that
    was a shove". Nothing answered the question the other two leave open,
    which is whether the fighter is on the ground and going somewhere: a fighter
    at a full run left nothing in the plane, so the most continuous movement in
    the game displaced nothing on screen while the shortest one left a ribbon.
    """
    groups = SpriteGroups()
    entity = _walker()
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)

    _walk(system, entity, Physics.PLAYER_SPEED, ticks=60)

    steps = _by_family(groups, "footstep_dust")
    assert steps, "a fighter at a full run leaves marks behind him"
    assert _by_family(groups, "dust_grain"), "and grit, or the mark is a smudge"


def test_a_fighter_standing_still_leaves_nothing() -> None:
    """Friction decays to zero over several ticks, and every one of them is a tick.

    Pacing by distance rather than by time is what keeps this from being a puff
    under a fighter who has already stopped -- there is no distance to pace.
    """
    groups = SpriteGroups()
    entity = _walker(speed=0.0)
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)

    _walk(system, entity, 0.0, ticks=60)

    assert not groups.fx_sprites, f"a standing fighter leaves nothing: {len(groups.fx_sprites)}"


def test_the_footstep_cadence_is_distance_and_not_frames(
    _spy_on_steps: _StepSpy,
) -> None:
    """The step belongs to the ground, so it is paced by ground covered.

    Pacing by time instead would space the marks by the stride rather than
    along the floor, which puts the slow tiers' marks closer together and reads
    as clustering rather than as walking. So the count has to follow the
    distance, and it has to follow it exactly while nothing is clamping: at the
    walk's pace the cadence ceiling is never reached, and a run of ticks that
    came out anywhere but ``distance / step_distance`` would mean the emitter
    was counting time or counting frames.
    """
    walk = FootstepDust.TIER[PlayerState.WALK.value]
    speed = Physics.PLAYER_SPEED * Locomotion.WALK_SLOW_PROMOTE
    groups = SpriteGroups()
    entity = _walker(speed=speed, state=PlayerState.WALK.value)
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)
    spy = _spy_on_steps
    spy.feet.clear()

    _walk(system, entity, speed, ticks=120)

    paced = speed * 2.0 / walk.step_distance
    assert abs(len(spy.feet) - paced) <= 1, (
        f"a walk is paced by distance: {len(spy.feet)} steps over {paced:.1f} strides"
    )


def test_a_walk_marks_the_floor_and_a_run_marks_it_twice_as_fast(
    _spy_on_steps: _StepSpy,
) -> None:
    """The whole claim of the tier table, measured as two rates.

    A run that is merely the same comb played faster reads as a walk sped up, so
    the gap has to be large enough to be a different gait -- and it is checked
    against the rate each tier actually gets rather than against the numbers as
    written, because ``MIN_STEP_EVERY`` is the thing that would quietly flatten
    the two rows back together.

    Both rates come out near their arithmetic: forty pixels of stride at a
    walker's pace is five steps a second, and the run is clamped from the
    twenty-five it asks for to the ceiling's twelve, landing at ten.
    """
    rates: dict[str, float] = {}
    for state, ratio in ((PlayerState.WALK.value, Locomotion.WALK_SLOW_PROMOTE), ("run", 1.0)):
        speed = Physics.PLAYER_SPEED * ratio
        groups = SpriteGroups()
        entity = _walker(speed=speed, state=state)
        groups.entity_sprites.add(entity)
        system = PhysicsSystem(groups)
        spy = _spy_on_steps
        spy.feet.clear()

        _walk(system, entity, speed, ticks=120)

        rates[state] = len(spy.feet) / 2.0

    assert 3.0 < rates[PlayerState.WALK.value] < 8.0, (
        f"a walk still marks the floor: {rates[PlayerState.WALK.value]:.1f} steps/s"
    )
    assert rates["run"] > rates[PlayerState.WALK.value] * 1.8, (
        f"and the run reads as a different gait: {rates['run']:.1f} against "
        f"{rates[PlayerState.WALK.value]:.1f} steps/s"
    )


def test_a_run_is_a_comb_of_marks_and_not_a_trail(
    _spy_on_steps: _StepSpy,
) -> None:
    """The one number that keeps the dash the fastest thing that leaves a mark.

    The run row asks for a step every fourteen pixels, which at
    ``Physics.PLAYER_SPEED`` is a mark every 0.04s -- twenty-five a second. That
    is not a comb: it is the dash's ribbon drawn small and in the dash's own
    lane, and holding a direction would leave the player permanently trailed,
    which is the one thing that would make the dash stop being an event.

    So the cadence is held down and what shows it is that the spacing opens up
    as the speed rises, rather than the step count keeping pace with the stride.
    """
    groups = SpriteGroups()
    speed = Physics.PLAYER_SPEED
    entity = _walker(speed=speed)
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)
    spy = _spy_on_steps
    spy.feet.clear()

    _walk(system, entity, speed, ticks=120)

    ceiling = 2.0 / FootstepDust.MIN_STEP_EVERY
    assert len(spy.feet) <= ceiling, f"{len(spy.feet)} steps in 2s under a {ceiling:.1f} ceiling"
    assert len(spy.feet) >= ceiling * 0.8, "and the ceiling is not the only thing holding it back"
    # Clamped, so the marks spread rather than the count tracking the stride.
    assert speed * 2.0 / len(spy.feet) > FootstepDust.TIER["run"].step_distance


def test_a_guard_shuffle_marks_nothing() -> None:
    """``walk_slow`` is silent, and it is the tier a guard drops into.

    ``Guard.MOVE_MULT`` is 0.35, which is under ``WALK_SLOW_PROMOTE``, so
    holding a stick forward puts the fighter in ``walk_slow`` -- which makes
    this the most common ground tier in the game by far, and the one that must
    not turn a block into a running start.

    It is silent by being absent from ``FootstepDust.TIER`` and named in
    ``FootstepDust.SILENT``, rather than by being below a speed threshold: a
    fighter easing out of a run passes through the same speeds without having
    become a guarded one. And the state machine is what decides, because it has
    hysteresis around the boundary and re-deriving the tier here from the
    velocity would put the flicker back -- at five steps a second that is a
    scuff blinking under a fighter who is barely moving.
    """
    groups = SpriteGroups()
    speed = Physics.PLAYER_SPEED * GuardSettings.MOVE_MULT
    entity = _walker(speed=speed, state=PlayerState.WALK_SLOW.value)
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)

    _walk(system, entity, speed, ticks=120)

    assert not groups.fx_sprites, (
        f"a guarded shuffle leaves no dust: {len(groups.fx_sprites)} particles"
    )
    assert PlayerState.WALK_SLOW.value in FootstepDust.SILENT
    assert PlayerState.WALK_SLOW.value not in FootstepDust.TIER


def test_a_run_scatters_its_step_further_than_a_walk_does() -> None:
    """Cadence alone is not gait: the mark has to open out as the pace goes up.

    Two puffs, and at a walk's spread they come out close enough under the heel
    to read as one smudge. At a run's they separate, which is what makes the
    faster comb read as a fighter driving rather than a fighter walking faster.

    Compared as the span between the two halves' sideways velocities, averaged
    over many spawns rather than read off one: the jitter is half the spread, so
    a single sample says more about the draw than about the setting.
    """
    spans: dict[str, float] = {}
    for state in (PlayerState.WALK.value, PlayerState.RUN.value):
        entity = _walker(state=state)
        tier = FootstepDust.TIER[state]
        draws = [
            [
                puff.velocity.x
                for puff in spawn_footstep_dust(
                    pygame.sprite.Group(), entity, foot=False, tier=tier
                )
            ]
            for _ in range(200)
        ]
        spans[state] = statistics.fmean(max(d) - min(d) for d in draws)

    assert spans[PlayerState.RUN.value] > spans[PlayerState.WALK.value] * 1.5, (
        f"a run's step opens out: {spans[PlayerState.RUN.value]:.1f} against "
        f"{spans[PlayerState.WALK.value]:.1f} px/s"
    )


def test_a_fighter_with_no_locomotion_tier_marks_the_floor_anyway() -> None:
    """Not in the table is not the same as silent, and only one of them is a setting.

    An enemy patrolling is not in ``walk_slow``, so folding "absent" into
    "silent" would leave it marking nothing -- and an enemy chasing you is the
    one other fighter in the frame whose dust is worth having. The two cases are
    told apart by ``FootstepDust.SILENT`` naming the tier that means it.

    So the untiered fallback is the run row, and this is what holds it there: an
    entity with no state machine at all gets the same dust, paced by its own
    speed, so nothing outside the table is a special case.
    """
    for state in ("chase", "patrol", None):
        groups = SpriteGroups()
        speed = Physics.PLAYER_SPEED * 0.5
        entity = _walker(speed=speed, state=state) if state else make_entity()
        if state is None:
            entity.speed = Physics.PLAYER_SPEED
            entity.velocity.x = speed
            entity.on_surface["floor"] = True
        groups.entity_sprites.add(entity)
        system = PhysicsSystem(groups)

        _walk(system, entity, speed, ticks=120)

        assert _by_family(groups, "footstep_dust"), f"an entity in {state!r} still marks the floor"


def test_the_two_feet_alternate(_spy_on_steps: _StepSpy) -> None:
    """One mark stamped down the middle of a path reads as one foot shuffling.

    The parity is the step counter the distance pacing already keeps, so the
    alternation costs no second clock -- and the alternation is the whole reason
    the spawner is handed a bool rather than asked to remember anything.
    """
    groups = SpriteGroups()
    entity = _walker()
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)
    spy = _spy_on_steps
    spy.feet.clear()

    _walk(system, entity, Physics.PLAYER_SPEED, ticks=120)

    assert spy.feet == [step % 2 == 0 for step in range(len(spy.feet))], (
        f"strict alternation, every step: {spy.feet}"
    )
    assert len(set(spy.feet)) == 2, "both feet get used"

    # And it starts on the same foot every time, so two fighters walking off the
    # same edge do not set off mid-stride against each other.
    groups.entity_sprites.remove(entity)
    other = _walker()
    groups.entity_sprites.add(other)
    spy.feet.clear()

    _walk(system, other, Physics.PLAYER_SPEED, ticks=120)

    assert spy.feet[0] is True, "the first step always lands on the same foot"
    assert spy.feet[1] is False, "and the second on the other one"


def test_a_stopped_fighter_lays_no_step_under_himself() -> None:
    """The plane is painted *under* the fighter, so a mark at his feet is invisible.

    A step born at the fighter's centre spends its first third of life behind
    him, and a footstep's life is short enough that the whole readable part of
    it would be there. The trailing edge is where a foot is when it is thrown.
    """
    groups = SpriteGroups()
    entity = _walker()
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)

    _walk(system, entity, Physics.PLAYER_SPEED, ticks=120)

    steps = _by_family(groups, "footstep_dust")
    behind = [sprite.rect.centerx < entity.hitbox.centerx for sprite in steps]
    assert all(behind), "every step is laid behind the fighter's centre"
    assert any(sprite.rect.right < entity.hitbox.centerx for sprite in steps), (
        "and clear of the body rather than only behind its centre"
    )


def test_a_walker_in_mid_air_leaves_nothing() -> None:
    """Same rule as the dash trail, and for the same reason.

    Dust needs something to come off. A mark hanging at the height of a jump
    reads as the fighter smearing the screen, and it is drawn under him, so it
    sits against the sky where nothing else in the plane does.
    """
    groups = SpriteGroups()
    entity = _walker(grounded=False)
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)

    _walk(system, entity, Physics.PLAYER_SPEED, ticks=120)

    assert not groups.fx_sprites


def test_a_walking_fighter_lays_no_step_under_his_own_dash() -> None:
    """The dash carries its own mark, and two marks at one movement is the old bug.

    A dash crosses a floor at 1100 px/s, so it satisfies every gate the footstep
    checks. Left in, it lays the trail's ribbon and a comb of steps in the same
    lane on the same ticks -- which is the white cloud under a stretched
    rectangle that ``test_a_dash_trails_dust_and_nothing_else`` is about.
    """
    groups = SpriteGroups()
    entity = _walker()
    entity.state_machine = SimpleNamespace(current_state_name="dash")
    entity.velocity.x = Physics.DASH_SPEED
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)

    _walk(system, entity, Physics.DASH_SPEED, ticks=int(Physics.DASH_DURATION * 60))

    assert not _by_family(groups, "footstep_dust"), "the trail is the dash's one mark"
    assert _by_family(groups, "dash_dust"), "and it is the one that is there"


def test_the_tick_a_landing_fires_carries_no_footstep() -> None:
    """A landing has a fan and a ground mark already, both at the feet.

    The footstep is the most frequent emission in the plane, so it is the one
    that would quietly pile onto whatever else is happening. A hard landing is
    the hardest read in the plane and a puff the fighter cannot see it put
    there takes away from it.
    """
    groups = SpriteGroups()
    entity = _walker()
    entity.landed_impact = Dust.MIN_FALL_SPEED + 100.0
    groups.entity_sprites.add(entity)
    system = PhysicsSystem(groups)

    entity.rect.x += Physics.PLAYER_SPEED * FootstepDust.TIER["run"].step_distance / 60.0
    system._spawn_impact_fx(1 / 60)

    families = [sprite.family for sprite in groups.fx_sprites]
    assert "landing_dust" in families, "the landing is not what got refused"
    assert "footstep_dust" not in families, "and the step under it yields"


def test_a_step_that_does_not_fit_the_budget_is_not_half_thrown() -> None:
    """Refused whole, for the reason the trail's is: a half step is a stutter.

    It also spends its own family's budget rather than the trail's, because a
    fighter at a run would otherwise be able to empty the cap a dash draws from
    and the dash would be the thing that gets truncated.
    """
    groups = SpriteGroups()
    entity = _walker()
    groups.entity_sprites.add(entity)
    cap = FX_FAMILY_BUDGETS["footstep_dust"]
    for _ in range(cap - 1):
        groups.fx_sprites.add(FootstepDustParticle((0.0, 0.0), (0.0, 0.0)))
    system = PhysicsSystem(groups)

    _walk(system, entity, Physics.PLAYER_SPEED, ticks=120)

    assert len(_by_family(groups, "footstep_dust")) == cap - 1


def test_a_walking_fighter_never_starves_the_dash_trail() -> None:
    """Two fighters, one plane: the busiest mark in the game yields to the event.

    The trail's own cap is the reason this is its own family and not a flag on
    the trail's. A cap shared with a mark that fires twelve times a second is a
    cap that spends itself, and the effect that gets truncated is the dash --
    which is the one thing a trail cannot afford to do halfway.
    """
    groups = SpriteGroups()
    walker = _walker()
    groups.entity_sprites.add(walker)
    for _ in range(FX_FAMILY_BUDGETS["footstep_dust"]):
        groups.fx_sprites.add(FootstepDustParticle((0.0, 0.0), (0.0, 0.0)))
    dasher = _dasher()
    groups.entity_sprites.add(dasher)
    system = PhysicsSystem(groups)

    system._spawn_impact_fx(1 / 60)

    assert len(_by_family(groups, "dash_dust")) == DashDust.BURST_COUNT


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
