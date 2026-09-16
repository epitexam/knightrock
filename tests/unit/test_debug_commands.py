"""Phase 5 test bench: debug commands + showcase attack catalog."""

from src.combat.attack_data import PLAYER_ATTACKS
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
    import pygame

    assert pygame.K_c == DEBUG_JUGGLE_KEY
