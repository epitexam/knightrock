"""Phase 5 test bench: debug commands + showcase attack catalog."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.combat.attack_data import PLAYER_ATTACKS
from src.core.colors import Colors
from src.core.display.framing import Framing
from src.core.level.systems.projectile_system import ProjectileSystem
from src.core.level.systems.spawn_system import (
    DEBUG_ATTACKS,
    DEBUG_JUGGLE_KEY,
    DEBUG_SHOTS,
    SpawnSystem,
)
from src.core.sprite_groups import SpriteGroups
from src.data.attacks import attack_definition_to_dict, read_attack_definition
from src.entities.projectile import FIREBOLT_CONFIG, PIERCING_BOLT_CONFIG
from src.physics.spatial_hash import SpatialHash
from tests.unit.helpers import make_entity


@pytest.fixture(scope="module", autouse=True)
def _headless_display() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1024, 768))


@pytest.fixture()
def world_ui():
    from src.ui.panel_renderer import PanelRenderer
    from src.ui.world_ui import WorldUI

    return WorldUI(PanelRenderer(pygame.display.get_surface()))


@pytest.fixture()
def camera():
    from src.core.rendering.camera import Camera as _Camera

    return _Camera(Framing(float(1024), float(768)))


def _player() -> object:
    return make_entity(faction="player", attacks=dict(PLAYER_ATTACKS))


def test_showcase_attacks_are_registered_on_player() -> None:
    for attack_name in DEBUG_ATTACKS.values():
        assert attack_name in PLAYER_ATTACKS


def test_showcase_attacks_use_phase5_features() -> None:
    twin = PLAYER_ATTACKS["twin_fangs"].phases[0]
    assert len(twin.extra_hitboxes) == 1  # #1 multi-hitbox

    sweep = PLAYER_ATTACKS["sweeping_arc"].phases[0]
    assert len(sweep.hitbox_keyframes) == 3  # #2 animated
    assert sweep.hitbox_at(0)[0] != sweep.hitbox_at(12)[0]

    launcher = PLAYER_ATTACKS["sky_launcher"].phases[0]
    assert launcher.hit.juggle_gravity_mult == 0.5  # #4 juggle
    assert launcher.hit.knockback.power[1] < 0  # upward launch

    slam = PLAYER_ATTACKS["otg_slam"].phases[0]
    assert slam.hit.otg_allowed is True  # #4 OTG


def test_showcase_attacks_survive_json_roundtrip() -> None:
    for name in ("twin_fangs", "sweeping_arc", "sky_launcher", "otg_slam"):
        raw = attack_definition_to_dict(PLAYER_ATTACKS[name])
        back = read_attack_definition(raw, f"test.{name}")
        assert back == PLAYER_ATTACKS[name]


def test_trigger_test_attack_starts_showcase_move() -> None:
    groups = SpriteGroups()
    system = SpawnSystem(groups)
    player = _player()

    assert system.trigger_test_attack(player, "twin_fangs") is True
    assert player.combat.is_attacking


def test_trigger_test_attack_rejects_unknown_name() -> None:
    system = SpawnSystem(SpriteGroups())
    assert system.trigger_test_attack(_player(), "nope") is False


def test_attack_replay_restarts_attack_when_idle() -> None:
    system = SpawnSystem(SpriteGroups())
    player = _player()

    assert system.toggle_attack_replay("twin_fangs") == "twin_fangs"
    assert system.trigger_test_attack(player, "twin_fangs")
    # Replay waits while the attack runs, then restarts once idle.
    system.tick_attack_replay(player)
    assert player.combat.is_attacking
    while player.combat.is_attacking:
        player.combat.update(1 / 60)
        player.combat.sync_attack_box()
        system.debug_cooldowns.clear()
        system.tick_attack_replay(player)
    # Drain the combat-side cooldown so start_attack may fire again.
    for _ in range(180):
        player.combat.update(1 / 60)
        player.combat.sync_attack_box()
        system.debug_cooldowns.clear()
        system.tick_attack_replay(player)
        if player.combat.is_attacking:
            break
    assert player.combat.is_attacking


def test_attack_replay_toggle_returns_state() -> None:
    system = SpawnSystem(SpriteGroups())
    assert system.attack_replay is None
    name = system.toggle_attack_replay()
    assert name is not None
    assert system.attack_replay == name
    assert system.toggle_attack_replay() is None
    assert system.attack_replay is None


def test_attack_replay_ignored_while_attacking_or_on_cooldown() -> None:
    system = SpawnSystem(SpriteGroups())
    player = _player()
    system.toggle_attack_replay("twin_fangs")

    # Cooldown armed: tick is a no-op even when idle.
    system.debug_cooldowns["twin_fangs"] = 0.5
    system.tick_attack_replay(player)
    assert not player.combat.is_attacking

    # Attacking: replay must not interrupt.
    system.debug_cooldowns.clear()
    assert system.trigger_test_attack(player, "twin_fangs")
    combat = player.combat
    started = combat.state.frame_counter
    system.tick_attack_replay(player)
    assert combat.state.frame_counter == started


def test_fire_test_projectile_needs_a_system() -> None:
    assert SpawnSystem(SpriteGroups()).fire_test_projectile(_player()) is None


def test_fire_test_projectile_spawns_with_player_faction() -> None:
    groups = SpriteGroups()
    system = SpawnSystem(groups, projectile_system=ProjectileSystem(groups))
    player = _player()

    projectile = system.fire_test_projectile(player, FIREBOLT_CONFIG)

    assert projectile is not None
    assert projectile in groups.projectile_sprites
    assert projectile.faction == "player"
    assert projectile.velocity.x > 0  # facing right by default


def test_fire_piercing_bolt_is_piercing() -> None:
    groups = SpriteGroups()
    system = SpawnSystem(groups, projectile_system=ProjectileSystem(groups))

    projectile = system.fire_test_projectile(_player(), PIERCING_BOLT_CONFIG)

    assert projectile is not None
    assert projectile.config.pierce is True


def test_debug_shot_bindings_cover_both_presets() -> None:
    assert set(DEBUG_SHOTS.values()) == {FIREBOLT_CONFIG, PIERCING_BOLT_CONFIG}


def test_spawn_juggle_dummy_is_airborne_and_rising() -> None:
    groups = SpriteGroups()
    system = SpawnSystem(groups)
    player = _player()

    dummy = system.spawn_juggle_dummy(player)

    assert dummy is not None
    assert dummy in groups.entity_sprites
    assert dummy in groups.combat_sprites
    assert dummy.velocity.y < 0
    assert dummy.on_surface["floor"] is False


def test_debug_juggle_key_is_bound() -> None:
    assert pygame.K_c == DEBUG_JUGGLE_KEY


# --- Runtime spawns join the collision grid --------------------------------
#
# These pin the regression the level-level wiring fixed. A grid assigned after
# the world is built never reaches an entity the spawner creates later, and the
# symptom is not an error: the enemy works, hits what it should, and quietly
# costs a scan of every collider in the level on every one of its sub-steps.


def test_a_spawned_enemy_is_wired_to_the_grid() -> None:
    groups = SpriteGroups()
    grid = SpatialHash(cell_size=128)
    system = SpawnSystem(groups, spatial_hash=grid)
    player = _player()

    system._spawn_enemy("goblin", player)

    spawned = [enemy for enemy in groups.entity_sprites if enemy is not player]
    assert spawned, "the spawner should have produced an enemy"
    for enemy in spawned:
        assert enemy.spatial_hash is grid


def test_a_juggle_dummy_is_wired_to_the_grid() -> None:
    groups = SpriteGroups()
    grid = SpatialHash(cell_size=128)
    system = SpawnSystem(groups, spatial_hash=grid)

    dummy = system.spawn_juggle_dummy(_player())

    assert dummy is not None
    assert dummy.spatial_hash is grid


def test_a_spawn_without_a_grid_still_works() -> None:
    """``None`` stays legal: standalone use is correct, only slower.

    The grid is an optimization, not a precondition, so a system built without
    one must keep producing working entities rather than raising.
    """
    groups = SpriteGroups()
    system = SpawnSystem(groups)

    dummy = system.spawn_juggle_dummy(_player())

    assert dummy is not None
    assert dummy.spatial_hash is None


def test_swept_ghost_draws_only_when_boxes_moved(world_ui, camera) -> None:
    from src.ui.world_ui import WorldUI

    surface = world_ui.surface
    attack_box = pygame.FRect(100, 100, 30, 20)
    combat = SimpleNamespace(
        attack_boxes=(attack_box,),
        swept_attack_boxes=lambda: (attack_box,),
        state=SimpleNamespace(attack_name=None),
        current_phase=None,
    )
    entity = SimpleNamespace(
        hitbox=pygame.FRect(60, 100, 40, 48),
        hurtbox=pygame.FRect(60, 100, 40, 48),
        hurtboxes=None,
        combat=combat,
        faction="player",
        otg_timer=0.0,
        gravity_scale=1.0,
    )
    # Sample where the camera actually puts the box: the overlay draws in screen
    # space, so a hardcoded window silently stops matching the box as soon as
    # ``GameplayCamera.ZOOM`` changes.
    drawn = pygame.Rect(camera.apply(attack_box))
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([entity], camera)
    box_pixels = sum(
        1
        for x in range(drawn.left, drawn.right)
        for y in range(drawn.top, drawn.bottom)
        if surface.get_at((x, y))[:3] == Colors.debug_attack_box
    )
    assert box_pixels > 0
    assert WorldUI._swept_boxes(combat, 1) == (pygame.FRect(100, 100, 30, 20),)


def test_swept_ghost_exposes_previous_origin(world_ui, camera) -> None:
    from src.ui.world_ui import WorldUI

    combat = SimpleNamespace(
        attack_boxes=(pygame.FRect(120, 100, 30, 20),),
        swept_attack_boxes=lambda: (pygame.FRect(100, 100, 50, 20),),
    )
    swept = WorldUI._swept_boxes(combat, 1)
    assert swept[0] != combat.attack_boxes[0]
    assert swept[0].width == 50.0


@pytest.mark.parametrize(
    ("density", "per_frame"),
    [
        (1.0, 3),
        (1.8889, 6),
        # Below one the timeline keeps its design size rather than thinning to
        # nothing: an overlay that vanishes is worse than one that is too big.
        (0.5, 3),
    ],
)
def test_attack_timeline_marks_phase_progress(world_ui, density: float, per_frame: int) -> None:
    """Phase progress, in pixels that belong to the target.

    The three pixels per frame are a *world* dimension like every other here,
    so they follow the density -- the same reason a hitbox outline does, and the
    same bug when it did not.
    """
    world_ui.renderer.set_surface(world_ui.renderer.surface, density)
    state = SimpleNamespace(attack_name="jab", frame_counter=2)
    phase = SimpleNamespace(startup_frames=4, active_frames=4, recovery_frames=4)
    assert world_ui.metrics.timeline_px_per_frame == per_frame
    assert world_ui._timeline_progress(state, "startup", phase) == 2 * per_frame
    assert world_ui._timeline_progress(state, "active", phase) == (4 + 2) * per_frame
    assert world_ui._timeline_progress(state, "recovery", phase) == (4 + 4 + 2) * per_frame


@pytest.mark.parametrize("density", [1.0, 1.25, 1.8889, 2.0, 3.3333])
def test_the_overlay_is_never_thinner_than_one_art_pixel(world_ui, density: float) -> None:
    """The regression that made F1 look like a dead key.

    A hitbox outline is one art pixel wide by design. Handed to pygame unscaled
    on a window where the world is drawn 1.9x larger, it arrived at 53% of its
    weight and vanished into the tile grid -- and the labels, the zone seals and
    the timeline with it, because every dimension in the layer had the same
    units mistake. Below a density of one it must not *shrink* either.
    """
    world_ui.renderer.set_surface(world_ui.renderer.surface, density)
    assert world_ui.stroke() == max(1, round(density))
    assert world_ui.metrics.zone_outline == max(1, round(density))
    assert world_ui.metrics.zone_boost_outline == max(1, round(2 * density))
    assert world_ui.metrics.timeline_bar_height >= 1
    assert world_ui.metrics.tier_gap >= 1


def test_metrics_panel_caches_counters_between_ticks(world_ui) -> None:
    world_ui.update_metrics(SimpleNamespace(pairs_tested=3, overlaps=2, contacts=1))
    world_ui.update_metrics(SimpleNamespace(pairs_tested=3, overlaps=2, contacts=1))
    assert world_ui.metrics_text == ()
    for _ in range(8):
        world_ui.update_metrics(SimpleNamespace(pairs_tested=9, overlaps=9, contacts=9))
    assert world_ui.metrics_text == ("pairs 9", "overlaps 9", "contacts 9")


def test_live_attack_text_formats_player_state(world_ui) -> None:
    from src.ui.world_ui import WorldUI

    player = SimpleNamespace(
        combat=SimpleNamespace(
            state=SimpleNamespace(attack_name="jab", sub_state="active", frame_counter=3)
        )
    )
    assert WorldUI._live_attack_text(player) == "jab active f3"
    assert WorldUI._live_attack_text(None) is None
    idle = SimpleNamespace(combat=SimpleNamespace(state=SimpleNamespace(attack_name=None)))
    assert WorldUI._live_attack_text(idle) is None


def test_combat_panel_renders_counters_with_live_state(world_ui) -> None:
    player = SimpleNamespace(
        combat=SimpleNamespace(
            state=SimpleNamespace(attack_name="jab", sub_state="startup", frame_counter=1)
        )
    )
    for _ in range(10):
        world_ui.update_metrics(SimpleNamespace(pairs_tested=2, overlaps=1, contacts=1))
    world_ui.note_clash((10.0, 10.0))
    world_ui.draw_metrics_panel(player=player, hit_stop=0.05)
    assert world_ui.metrics_text == ("pairs 2", "overlaps 1", "contacts 1")
    assert world_ui._clash_ttl > 0.0


def test_note_clash_keeps_fresh_point_and_ignores_none(world_ui) -> None:
    world_ui.note_clash((42.0, 7.0))
    assert world_ui.clash_point == (42.0, 7.0)
    assert world_ui._clash_ttl > 0.0
    world_ui.note_clash(None)
    assert world_ui.clash_point == (42.0, 7.0)


def test_clash_marker_draws_gold_ring_then_decays(world_ui, camera) -> None:
    from src.ui.world_ui import CLASH_MARKER_LIFETIME, WorldUI

    surface = world_ui.surface
    surface.fill((0, 0, 0))
    world_ui.note_clash((120.0, 110.0))
    assert world_ui._clash_ttl == CLASH_MARKER_LIFETIME
    world_ui._draw_clash_marker(camera)
    gold_pixels = sum(
        1
        for x in range(90, 150)
        for y in range(80, 140)
        if surface.get_at((x, y))[:3] == Colors.gold
    )
    assert gold_pixels > 0

    surface.fill((0, 0, 0))
    for _ in range(30):
        world_ui._draw_clash_marker(camera)
    assert world_ui._clash_ttl <= 0.0
    surface.fill((0, 0, 0))
    world_ui._draw_clash_marker(camera)
    assert (
        sum(
            1
            for x in range(90, 150)
            for y in range(80, 140)
            if surface.get_at((x, y))[:3] == Colors.gold
        )
        == 0
    )
    assert WorldUI._draw_clash_marker  # bound method still wired in overlays
