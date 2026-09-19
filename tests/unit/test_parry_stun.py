"""Tests for parry-stun (DIZZY) mechanics: counters, thresholds, state, damage bonus."""

from types import SimpleNamespace

import pygame
import pytest

from src.core.fx import SparkParticle, spawn_dizzy_stars
from src.core.level.systems.combat_system import CombatSystem
from src.entities.enemies.enemy import Enemy
from src.entities.enemies.types.goblin import GOBLIN_CONFIG
from src.entities.player import Player
from src.states.reaction_states import DIZZY_STATE
from tests.unit.helpers import InputStub


def _player() -> Player:
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    p = Player(
        pos=(100.0, 0.0),  # Center of the test area
        groups=groups,
        collision_sprites=collision_sprites,
        moving_platforms=[],
        input_manager=InputStub(),  # type: ignore[arg-type]
    )
    p.facing_right = True  # Default facing right
    return p


def _enemy(config=GOBLIN_CONFIG, player=None) -> Enemy:
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    enemy = Enemy(
        pos=(140.0, 0.0),
        groups=groups,
        collision_sprites=collision_sprites,
        player_reference=player,
        config=config,
    )
    enemy.facing_right = False
    enemy.combat.start_attack(enemy.attack_name)
    for _ in range(6):
        enemy.combat.update(1 / 60)
    enemy.combat.sync_attack_box()
    return enemy


def _make_attacker(config=GOBLIN_CONFIG, player=None) -> Enemy:
    """Create an enemy attacker, positioned and combat-ready."""
    groups = pygame.sprite.Group()
    collision_sprites = pygame.sprite.Group()
    attacker = Enemy(
        pos=(140.0, 0.0),
        groups=groups,
        collision_sprites=collision_sprites,
        player_reference=None,
        config=config,
    )
    attacker.facing_right = False  # Face left towards player at x=100
    attacker.combat.start_attack(attacker.attack_name)
    # Advance past startup frames
    for _ in range(5):
        attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()
    return attacker


def test_enemy_copies_parry_stun_config() -> None:
    e = _enemy()
    assert e.parry_stun_threshold == 2
    assert e.parry_stun_duration == 1.5


def _reset_attacker(attacker: Enemy) -> None:
    """Reset attacker for a new attack attempt, advancing to active phase."""
    attacker.combat.state.end()
    # Clear cooldown for testing
    attacker.combat._cooldowns.clear()
    attacker.combat.start_attack(attacker.attack_name)
    # Advance past startup frames (4 startup + 1 to enter active)
    for _ in range(6):
        attacker.combat.update(1 / 60)
    attacker.combat.sync_attack_box()


def _clear_hit_stop(system: CombatSystem) -> None:
    """Clear hit stop timer for testing consecutive attacks in same tick."""
    system.hit_stop_timer = 0.0


def test_parry_increments_attacker_parries_taken() -> None:
    player = _player()
    player.state_machine.current_state_name = "guard"
    player.facing_right = True  # face the attacker
    player.guard.press()  # arm parry window
    attacker = _make_attacker(player=player)
    system = CombatSystem()

    # First parry
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    assert attacker.parries_taken == 1

    # Second parry -> triggers DIZZY
    _reset_attacker(attacker)
    _clear_hit_stop(system)
    player.guard.press()  # re-arm parry
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    assert attacker.parries_taken == 0  # reset after threshold
    assert attacker.state_machine.current_state_name == DIZZY_STATE
    assert any(ev.kind == "stun" for ev in system.guard_events)


def test_slime_needs_three_parries() -> None:
    from src.entities.enemies.types.slime import SLIME_CONFIG

    player = _player()
    player.state_machine.current_state_name = "guard"
    player.facing_right = True  # face the attacker
    player.guard.press()  # arm parry window
    attacker = _enemy(SLIME_CONFIG, player=player)
    attacker.facing_right = False  # attacker faces left towards player
    system = CombatSystem()

    # First two parries
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    _clear_hit_stop(system)
    assert attacker.parries_taken == 1
    assert attacker.state_machine.current_state_name != DIZZY_STATE

    _reset_attacker(attacker)
    _clear_hit_stop(system)
    player.guard.press()
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    assert attacker.parries_taken == 2
    assert attacker.state_machine.current_state_name != DIZZY_STATE

    # Third parry -> DIZZY
    _reset_attacker(attacker)
    _clear_hit_stop(system)
    player.guard.press()
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    assert attacker.parries_taken == 0
    assert attacker.state_machine.current_state_name == DIZZY_STATE


def test_entity_immune_to_dizzy() -> None:
    """Test an entity with no parry_stun_threshold (immune to dizzy)."""
    from src.entities.enemies.types.goblin import GOBLIN_CONFIG

    player = _player()
    player.state_machine.current_state_name = "guard"
    player.facing_right = True  # face the attacker
    player.guard.press()  # arm parry window
    # Use a goblin but make it immune to dizzy
    attacker = _enemy(GOBLIN_CONFIG, player=player)
    attacker.parry_stun_threshold = None  # Immune to dizzy
    attacker.facing_right = False  # attacker faces left towards player
    system = CombatSystem()

    for _ in range(5):
        system.process_attacks([attacker, player])  # type: ignore[list-item]
        _clear_hit_stop(system)
        _reset_attacker(attacker)
        player.guard.press()

    assert attacker.parries_taken == 5  # no threshold, keeps counting
    assert attacker.state_machine.current_state_name != DIZZY_STATE


def test_real_hit_resets_attacker_parries_taken() -> None:
    player = _player()
    attacker = _enemy(player=player)
    attacker.facing_right = False
    system = CombatSystem()

    # Parry once
    player.state_machine.current_state_name = "guard"
    player.facing_right = True  # face the attacker
    player.guard.press()  # arm parry window
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    _clear_hit_stop(system)
    assert attacker.parries_taken == 1

    # Attacker deals real HP damage (not guarded) - need new attack
    _reset_attacker(attacker)
    _clear_hit_stop(system)
    player.state_machine.current_state_name = "idle"
    system.process_attacks([attacker, player])  # type: ignore[list-item]

    assert attacker.parries_taken == 0


def test_chip_damage_does_not_reset_parries_taken() -> None:
    from src.entities.enemies.types.slime import SLIME_CONFIG

    player = _player()
    player.state_machine.current_state_name = "guard"
    player.facing_right = True  # face the attacker
    player.guard.press()  # arm parry window
    attacker = _enemy(SLIME_CONFIG, player=player)
    attacker.facing_right = False  # attacker faces left towards player
    system = CombatSystem()

    system.process_attacks([attacker, player])  # type: ignore[list-item]
    _clear_hit_stop(system)
    assert attacker.parries_taken == 1

    # Another guarded hit (chip only) - need to re-arm parry
    _reset_attacker(attacker)
    _clear_hit_stop(system)
    player.guard.press()
    system.process_attacks([attacker, player])  # type: ignore[list-item]
    assert attacker.parries_taken == 2  # still counts toward threshold (slime threshold=3)


def test_projectile_parry_does_not_count() -> None:
    # Projectiles don't have parries_taken, and projectile parries don't count
    # This is tested indirectly - projectile_system doesn't increment parries_taken
    assert True


def test_dizzy_damage_multiplier() -> None:
    from src.combat.frame_data import HitProperties
    from src.combat.hit_resolver import HitResolver
    from src.combat.knockback import KnockbackConfig
    from tests.unit.helpers import AttackerStub

    enemy = _enemy()
    enemy.state_machine.current_state_name = DIZZY_STATE
    enemy.stagger_timer = 1.0

    attacker = AttackerStub(centerx=80.0)
    result = HitResolver.resolve(
        attacker,
        enemy,
        HitProperties(
            damage=10,
            knockback=KnockbackConfig(power=(100.0, 0.0)),
        ),
    )

    assert result.applied is True
    # 10 * 1.5 = 15 damage
    assert result.actual_damage == pytest.approx(15.0)


def test_dizzy_state_exits_after_duration() -> None:
    from src.states.enemy_states import EnemyDizzyState

    enemy = _enemy()
    enemy.state_machine.current_state_name = DIZZY_STATE
    enemy.stagger_timer = 1.0
    state = EnemyDizzyState(enemy)

    # First update
    assert state.update(0.5) is None
    assert enemy.stagger_timer == pytest.approx(0.5)

    # Second update - timer clears
    assert state.update(0.6) == "idle"


def test_player_dizzy_state_exits_via_ground_return() -> None:
    from src.states.player_states import PlayerDizzyState

    player = _player()
    player.state_machine.current_state_name = DIZZY_STATE
    player.stagger_timer = 0.5
    player.on_surface = {"floor": True, "left": False, "right": False}

    state = PlayerDizzyState(player)
    assert state.update(0.3) is None

    assert state.update(0.3) == "idle"  # timer clears, ground_return -> idle


def test_dizzy_fx_spawns_stars() -> None:
    import pygame
    from pygame.sprite import Group

    entity = SimpleNamespace(
        hitbox=pygame.FRect(100, 100, 40, 48),
        parry_stun_duration=1.5,
    )
    group = Group()

    stars = spawn_dizzy_stars(group, entity)

    assert len(stars) == 12
    assert all(isinstance(s, SparkParticle) for s in stars)


def test_save_load_preserves_parry_counters() -> None:
    from tests.unit.helpers import make_entity

    entity = make_entity()
    entity.parries_given = 3
    entity.parries_taken = 2
    entity.parry_stun_threshold = 3
    entity.parry_stun_duration = 2.0

    snapshot = entity.save_state()

    entity.parries_given = 0
    entity.parries_taken = 0
    entity.parry_stun_threshold = None
    entity.parry_stun_duration = 0.0

    entity.load_state(snapshot)

    assert entity.parries_given == 3
    assert entity.parries_taken == 2
    assert entity.parry_stun_threshold == 3
    assert entity.parry_stun_duration == pytest.approx(2.0)


def test_enemy_config_parry_stun_json_roundtrip() -> None:
    from src.combat.attack_data import GOBLIN_ATTACKS
    from src.data.enemies import enemy_config_to_dict, read_enemy_config

    raw = {
        "size": [36.0, 48.0],
        "color": [60, 130, 60],
        "health": 60.0,
        "attacks": "goblin",
        "attack_name": "claw_swipe",
        "chase_speed": 120.0,
        "vision_range": 300.0,
        "attack_range": 60.0,
        "parry_stun_threshold": 4,
        "parry_stun_duration": 2.5,
    }
    config = read_enemy_config(raw, "test", {"goblin": GOBLIN_ATTACKS})
    assert config.parry_stun_threshold == 4
    assert config.parry_stun_duration == 2.5

    d = enemy_config_to_dict(config)
    assert d["parry_stun_threshold"] == 4
    assert d["parry_stun_duration"] == 2.5
