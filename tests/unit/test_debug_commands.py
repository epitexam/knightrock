"""Phase 5 test bench: debug commands + showcase attack catalog."""

import os
from types import SimpleNamespace

import pygame
import pytest

from src.combat.attack_data import PLAYER_ATTACKS
from src.core.colors import Colors
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

    return _Camera(1024, 768)


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


def test_swept_ghost_draws_only_when_boxes_moved(world_ui, camera) -> None:
    from src.ui.world_ui import WorldUI

    surface = world_ui.display_surface
    combat = SimpleNamespace(
        attack_boxes=(pygame.FRect(100, 100, 30, 20),),
        swept_attack_boxes=lambda: (pygame.FRect(100, 100, 30, 20),),
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
    surface.fill((0, 0, 0))
    world_ui.draw_debug_overlays([entity], camera)
    box_pixels = sum(
        1
        for x in range(100, 130)
        for y in range(100, 120)
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


def test_attack_timeline_marks_phase_progress(world_ui) -> None:
    from src.ui.world_ui import WorldUI

    state = SimpleNamespace(attack_name="jab", frame_counter=2)
    phase = SimpleNamespace(startup_frames=4, active_frames=4, recovery_frames=4)
    assert WorldUI._timeline_progress(state, "startup", phase) == 2 * 3
    assert WorldUI._timeline_progress(state, "active", phase) == (4 + 2) * 3
    assert WorldUI._timeline_progress(state, "recovery", phase) == (4 + 4 + 2) * 3


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

    surface = world_ui.display_surface
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
